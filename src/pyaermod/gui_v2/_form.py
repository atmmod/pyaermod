"""
Shared dataclass-field → NiceGUI widget helper.

Used by every tab that edits a dataclass (sources, receptors,
meteorology, output, control). Keeps the per-tab page modules
small — each just lists which fields to render and the form helper
emits the right widget by introspecting the dataclass.

Field-type → widget mapping (:func:`field_kind`)
-----------------------------------------------

=======================================  =========================================
Annotation                               Widget
=======================================  =========================================
``str`` / ``Optional[str]``              ``ui.input``; full width when the field
                                         names a file (``*_file``, ``postfile``)
``float`` / ``Optional[float]``          ``ui.number`` (clearable when Optional)
``int`` / ``Optional[int]``              integer ``ui.number`` that stores ``int``
``bool``                                 ``ui.checkbox``
``List[Tuple[float, float]]``            text area (one ``x, y`` pair per line)
``List[str]``                            text area (one entry per line)
``List[float]`` / ``Optional[...]``      text area (one value per line)
``Optional[Union[float, List[float]]]``  ``ui.number`` (clearable) while the
                                         current value is a scalar or ``None``;
                                         text area (one value per line) once it
                                         already holds a list or tuple
anything else                            read-only summary: lists of dataclasses
                                         or other tuples, enums, nested objects
=======================================  =========================================

Every label carries the field's units ("Stack temp (K)") and every input
shows its help text, both from the field metadata the library records
with :func:`pyaermod._fields.described`. A number box never writes None
into a field that is not Optional: emptying it shows "Required" and keeps
the value. :func:`emit_fields` lays fields out in a grid of one to three
columns, depending on the width of the window.

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
import enum
import types
import typing
from typing import Any, Callable, Iterable, Optional, Tuple, Union

from .._fields import help_of, units_of

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


def _matches_scalar_or_list_type(tp: Any) -> bool:
    """True for a resolved union admitting a numeric scalar *and* a numeric list."""
    origin = typing.get_origin(tp)
    if origin is not Union and origin is not types.UnionType:
        return False     # a bare ``float`` or ``List[float]`` is not this shape
    args = typing.get_args(tp)
    non_none = [a for a in args if a is not type(None)]
    if not all(a in _NUMERIC_TYPES or _is_numeric_list_type(a) for a in non_none):
        return False
    if not any(a in _NUMERIC_TYPES for a in non_none):
        return False
    return any(_is_numeric_list_type(a) for a in non_none)


def _matches_scalar_or_list_str(annotation: str) -> bool:
    """Structural equivalent of :func:`_matches_scalar_or_list_type`."""
    try:
        node = ast.parse(annotation.strip(), mode="eval").body
    except SyntaxError:
        return False
    names = _leaf_names(node)
    non_none = [n for n in names if n != "None"]
    if not all(n in ("int", "float", _NUMERIC_LIST_LEAF) for n in non_none):
        return False
    if not any(n in ("int", "float") for n in non_none):
        return False
    return _NUMERIC_LIST_LEAF in non_none


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
        return _matches_scalar_or_list_str(annotation)
    return _matches_scalar_or_list_type(annotation)


_HINTS_CACHE: dict = {}


def _type_hints(cls: type) -> dict:
    """Resolved annotations for ``cls`` (empty if a forward ref cannot be resolved)."""
    if cls not in _HINTS_CACHE:
        try:
            _HINTS_CACHE[cls] = typing.get_type_hints(cls)
        except (NameError, AttributeError):
            # An unresolvable forward reference, and only that. Real case in
            # this codebase: ``pathways.ChemistryOptions.olm_groups`` is
            # ``List[SourceGroupDefinition]`` and the name is imported only
            # under ``if TYPE_CHECKING`` -> NameError. AttributeError is the
            # dotted-name sibling (``mod.Missing``). ``TypeError`` is *not*
            # caught: get_type_hints raises it for a non-class argument, and
            # ``cls`` here is always ``type(obj)``, so it would mean a bug
            # worth seeing rather than a field worth falling back on.
            # Falling back to {} sends the caller to ``fmeta.type``, the raw
            # string annotation, which the structural parsers above handle.
            _HINTS_CACHE[cls] = {}
    return _HINTS_CACHE[cls]


def resolve_annotation(obj: Any, fmeta) -> Any:
    """The resolved type of field ``fmeta`` on ``obj``, else its raw annotation."""
    return _type_hints(type(obj)).get(fmeta.name, fmeta.type)


# ---------------------------------------------------------------------
# Which widget a field gets
# ---------------------------------------------------------------------

#: Field kinds (:func:`field_kind`).
TEXT, PATH, BOOL, INT, FLOAT = "text", "path", "bool", "int", "float"
SCALAR_OR_LIST, VERTICES, STR_LIST, NUMBER_LIST, READ_ONLY = (
    "scalar_or_list", "vertices", "str_list", "number_list", "read_only")

#: Field names that hold a file name or path (full-width inputs).
_PATH_NAMES = frozenset({"eventfil", "postfile"})


def _is_path_name(name: str) -> bool:
    return name.endswith("_file") or name in _PATH_NAMES


def _args_without_none(tp: Any) -> Tuple[list, bool]:
    origin = typing.get_origin(tp)
    if origin is Union or origin is types.UnionType:
        args = list(typing.get_args(tp))
        non_none = [a for a in args if a is not type(None)]
        return non_none, len(non_none) < len(args)
    return [tp], False


def _list_item(tp: Any) -> Any:
    """The item type of ``List[X]`` / ``Optional[List[X]]``, else a sentinel."""
    non_none, _ = _args_without_none(tp)
    if len(non_none) == 1 and typing.get_origin(non_none[0]) is list:
        args = typing.get_args(non_none[0])
        return args[0] if len(args) == 1 else _NOT_A_LIST
    return _NOT_A_LIST


_NOT_A_LIST = object()


def _str_kind(type_str: str) -> Optional[str]:
    """The kind of a field whose annotation could not be resolved."""
    compact = type_str.replace(" ", "").replace("typing.", "")
    if compact in ("str", "Optional[str]"):
        return TEXT
    if compact == "bool":
        return BOOL
    if compact in ("List[Tuple[float,float]]", "list[tuple[float,float]]"):
        return VERTICES
    if compact in ("List[str]", "list[str]", "Optional[List[str]]"):
        return STR_LIST
    if compact in ("List[float]", "list[float]", "Optional[List[float]]", "List[int]"):
        return NUMBER_LIST
    return None


def _allows_none(annotation: Any) -> bool:
    """Whether a field's annotation admits None (resolved or as a string)."""
    if isinstance(annotation, str):
        compact = annotation.replace(" ", "")
        return compact.startswith(("Optional[", "typing.Optional[")) or "None" in compact
    return _args_without_none(annotation)[1]


def is_integer(annotation: Any) -> bool:
    """True for ``int`` / ``Optional[int]`` (resolved or as a string); False for floats."""
    if isinstance(annotation, str):
        try:
            node = ast.parse(annotation.strip(), mode="eval").body
        except SyntaxError:
            return False
        names = [n for n in _leaf_names(node) if n != "None"]
        return bool(names) and all(n == "int" for n in names)
    non_none, _ = _args_without_none(annotation)
    return bool(non_none) and all(a is int for a in non_none)


def field_kind(obj: Any, fmeta) -> str:
    """Which widget :func:`emit_field` builds for field ``fmeta`` of ``obj``.

    One of :data:`TEXT`, :data:`PATH` (text that names a file, shown full
    width), :data:`BOOL`, :data:`INT`, :data:`FLOAT`,
    :data:`SCALAR_OR_LIST` (the building-downwash shape),
    :data:`VERTICES` (``List[Tuple[float, float]]``), :data:`STR_LIST`,
    :data:`NUMBER_LIST` (``List[float]``, optionally ``None``) or
    :data:`READ_ONLY`: every other list (of dataclasses, of other tuples,
    of lists), enums and nested dataclasses, which have no editor yet and
    are shown, not edited.
    """
    annotation = resolve_annotation(obj, fmeta)
    if isinstance(annotation, str):
        kind = _str_kind(annotation)
        if kind is None:
            if is_numeric_or_numeric_list(annotation):
                kind = SCALAR_OR_LIST
            elif is_numeric(annotation):
                kind = INT if is_integer(annotation) else FLOAT
            else:
                kind = READ_ONLY
    else:
        non_none, _ = _args_without_none(annotation)
        item = _list_item(annotation)
        if non_none == [str]:
            kind = TEXT
        elif non_none == [bool]:
            kind = BOOL
        elif item is not _NOT_A_LIST:
            if item is str:
                kind = STR_LIST
            elif item in _NUMERIC_TYPES:
                kind = NUMBER_LIST
            elif (typing.get_origin(item) is tuple
                  and list(typing.get_args(item)) == [float, float]):
                kind = VERTICES
            else:
                kind = READ_ONLY
        elif is_numeric_or_numeric_list(annotation):
            kind = SCALAR_OR_LIST
        elif is_numeric(annotation):
            kind = INT if is_integer(annotation) else FLOAT
        else:
            kind = READ_ONLY
    if kind == TEXT and _is_path_name(fmeta.name):
        return PATH
    return kind


def field_label(fmeta) -> str:
    """A field's label: its name in words, and its units in brackets.

    ``stack_temp`` with units ``K`` is "Stack temp (K)"; ``source_id`` is
    "Source ID"; a count (units ``""``) or a name has no brackets.
    """
    words = fmeta.name.split("_")
    words = ["ID" if w == "id" else w for w in words]
    text = " ".join(words)
    text = text[:1].upper() + text[1:]
    units = units_of(fmeta)
    return f"{text} ({units})" if units else text


def _summary(value: Any) -> str:
    """How a read-only field shows its value."""
    if value is None:
        return "not set"
    if isinstance(value, (list, tuple)):
        if not value:
            return "none"
        noun = "item" if len(value) == 1 else "items"
        return f"{len(value)} {noun}"
    if isinstance(value, enum.Enum):
        return str(value.value)
    if dataclasses.is_dataclass(value):
        return type(value).__name__
    return str(value)


# ---------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------

def _notify_on_edit(widget, on_change: Optional[Callable[[], None]]) -> None:
    """Call ``on_change()`` whenever the user changes ``widget``'s value.

    Attached *after* ``bind_value``, so the binding's initial sync from the
    object is not mistaken for an edit.
    """
    if on_change is None:
        return
    widget.on_value_change(lambda _e: on_change())


def _add_help(widget, fmeta) -> None:
    """Show the field's help text under the input (Quasar's ``hint``)."""
    text = help_of(fmeta)
    if text:
        widget.props["hint"] = text


def _textarea(parent, obj, fmeta, label: str, text: str, parse: Callable[[str], Any],
              on_change: Optional[Callable[[], None]], placeholder: str = "") -> None:
    from nicegui import ui

    with parent:
        ta = ui.textarea(label=label, value=text, placeholder=placeholder or None).classes("w-full")
        _add_help(ta, fmeta)

    def _save(_=None) -> None:
        setattr(obj, fmeta.name, parse(ta.value or ""))
        if on_change is not None:
            on_change()

    ta.on("update:model-value", _save)


def _parse_pairs(text: str) -> list:
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        parts = [p.strip() for p in s.replace(";", ",").split(",")]
        if len(parts) >= 2:
            with contextlib.suppress(ValueError):
                rows.append((float(parts[0]), float(parts[1])))
    return rows


def _parse_numbers(text: str) -> list:
    values = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        with contextlib.suppress(ValueError):
            values.append(float(s))
    return values


def _number(parent, obj, fmeta, label: str, *, integer: bool, optional: bool,
            on_change: Optional[Callable[[], None]]) -> None:
    """A number box that stores what the field's type allows.

    An integer field gets an integer box (no decimals) and stores an
    ``int``, so the project holds ``14735``, not ``14735.0``. A field
    that is not Optional is never set to None: emptying the box shows
    "Required" and leaves the value as it was. There is no display
    ``format``: ui.number rewrites its value to the format when it loses
    focus, and the binding writes that back, which once turned an emission
    rate of 1.5e-6 into 0.0.
    """
    from nicegui import ui

    fname = fmeta.name

    def to_model(value: Any) -> Any:
        if value is None:
            return None if optional else getattr(obj, fname)
        if integer:
            return round(float(value))
        return value

    with parent:
        box = ui.number(label=label, value=getattr(obj, fname),
                        validation=None if optional else {"Required": lambda v: v is not None})
        if integer:
            box.props["precision"] = 0
            box.props["step"] = 1
        if optional:
            box.props["clearable"] = True
        _add_help(box, fmeta)
        box.classes("w-full").bind_value(obj, fname, forward=to_model)
        _notify_on_edit(box, on_change)


def emit_field(parent, obj: Any, fmeta, *,
               on_change: Optional[Callable[[], None]] = None) -> None:
    """Render the right widget for a single dataclass field.

    ``parent`` is a NiceGUI container; the widget is added to it, full
    width. The widget changes ``obj`` in place whenever the user changes
    the value, and then calls ``on_change()`` if given (never while the
    widget is being built). The label carries the field's units and the
    help text shows under the input, both from the field's metadata
    (:mod:`pyaermod._fields`).
    """
    from nicegui import ui

    fname = fmeta.name
    kind = field_kind(obj, fmeta)
    cur = getattr(obj, fname)
    label = field_label(fmeta)
    optional = _allows_none(resolve_annotation(obj, fmeta))

    if kind in (TEXT, PATH):
        # Optional[str] fields (OutputPathway.summary_file, plot_file, ...)
        # are plain text inputs too; an empty box reads back as "".
        with parent:
            box = ui.input(label=label, value=cur or "").classes("w-full").bind_value(obj, fname)
            _add_help(box, fmeta)
            _notify_on_edit(box, on_change)
    elif kind == BOOL:
        with parent:
            box = ui.checkbox(label, value=bool(cur)).bind_value(obj, fname)
            text = help_of(fmeta)
            if text:
                with box:
                    ui.tooltip(text)
            _notify_on_edit(box, on_change)
    elif kind == VERTICES:
        # Dispatched before the numeric kinds on purpose: polygon vertices
        # once crashed the editor as a ``ui.number``.
        _textarea(parent, obj, fmeta, label,
                  "\n".join(f"{x:g}, {y:g}" for x, y in (cur or [])), _parse_pairs, on_change)
    elif kind == STR_LIST:
        _textarea(parent, obj, fmeta, label, "\n".join(str(v) for v in (cur or [])),
                  lambda text: [s.strip() for s in text.splitlines() if s.strip()], on_change)
    elif kind == NUMBER_LIST:
        # One value per line; an emptied box is None where the field allows it.
        def parse(text: str) -> Any:
            values = _parse_numbers(text)
            return values if values or not optional else None

        _textarea(parent, obj, fmeta, label, "\n".join(f"{v:g}" for v in (cur or [])),
                  parse, on_change, placeholder="one value per line")
    elif kind == SCALAR_OR_LIST:
        # Building downwash (``Optional[Union[float, List[float]]]``): one
        # value for every direction, or 36 -- one per 10-degree wind
        # sector. The widget follows the *current* value so neither shape
        # is destroyed by rendering. Emptying either one stores None: the
        # writer emits the keyword for anything that is not None, and an
        # empty list would be rejected as "not 36 values".
        if isinstance(cur, (list, tuple)):
            _textarea(parent, obj, fmeta, label, "\n".join(f"{v:g}" for v in cur),
                      lambda text: _parse_numbers(text) or None, on_change,
                      placeholder="one value per 10-degree sector")
        else:
            _number(parent, obj, fmeta, label, integer=False, optional=True, on_change=on_change)
    elif kind in (INT, FLOAT):
        _number(parent, obj, fmeta, label, integer=kind == INT, optional=optional,
                on_change=on_change)
    else:
        # No editor yet (lists of dataclasses or tuples, enums, nested
        # dataclasses): shown, never edited, so a free-text box cannot turn
        # them into strings the project file refuses.
        with parent:
            ui.label(f"{label}: {_summary(cur)}").classes("text-grey-8")


#: Kinds that take the full width of a form's grid.
_WIDE = frozenset({PATH, VERTICES, STR_LIST, NUMBER_LIST, READ_ONLY})


def emit_fields(obj: Any, fmetas: Iterable[Any], *,
                on_change: Optional[Callable[[], None]] = None) -> None:
    """Render several fields of ``obj`` as a responsive grid in the current container.

    One column on a phone, two from 600 px and three from 1024 px; paths,
    lists and read-only summaries span the whole row.
    """
    from nicegui import ui

    with ui.element("div").classes(
        "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-3 w-full items-start"
    ):
        for fmeta in fmetas:
            wide = field_kind(obj, fmeta) in _WIDE
            cell = ui.element("div").classes("col-span-full" if wide else "min-w-0")
            emit_field(cell, obj, fmeta, on_change=on_change)


def emit_form(
    container, obj: Any, *, fields: Optional[Iterable[str]] = None,
    on_change: Optional[Callable[[], None]] = None,
) -> None:
    """Render every field of ``obj`` as a form inside ``container``.

    ``fields`` optionally restricts to a subset, preserving order (unknown
    names are skipped). ``on_change`` is passed to every :func:`emit_field`.
    """
    name_to_meta = {f.name: f for f in dataclasses.fields(obj)}
    chosen = list(fields) if fields else list(name_to_meta.keys())
    with container:
        emit_fields(obj, [name_to_meta[n] for n in chosen if n in name_to_meta],
                    on_change=on_change)


__all__ = [
    "BOOL",
    "FLOAT",
    "INT",
    "NUMBER_LIST",
    "PATH",
    "READ_ONLY",
    "SCALAR_OR_LIST",
    "STR_LIST",
    "TEXT",
    "VERTICES",
    "emit_field",
    "emit_fields",
    "emit_form",
    "field_kind",
    "field_label",
    "is_integer",
    "is_numeric",
    "is_numeric_or_numeric_list",
    "is_optional_numeric",
    "resolve_annotation",
]

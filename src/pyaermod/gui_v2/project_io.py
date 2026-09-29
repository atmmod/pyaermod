"""
JSON save/load for the project a GUI v2 :class:`~pyaermod.gui_v2.session.Session` edits.

UI-framework-agnostic: the legacy Streamlit ``ProjectSerializer`` is
tightly coupled to ``st.session_state`` and lives in :mod:`pyaermod.gui`.
This module is the headless equivalent — both GUIs can converge on it
once Streamlit is deprecated in v2.0.

Format
------

Top-level JSON dict::

    {
      "pyaermod_version": "1.9.0",
      "save_format_version": 1,
      "project": <AERMODProject as a tree of JSON objects>
    }

Every dataclass is a JSON object of its fields plus a ``_type`` tag naming
its class, so a list of sources (or a field holding a subclass) reads back
as the right class. Enums are ``{"_enum": "EnumClass.MEMBER"}``, tuples are
lists, and a dict whose keys are not all strings is
``{"_items": [[key, value], ...]}``.

Reading is driven by the dataclass annotations, not by the file: each
value is checked against the type of the field it fills and nested
dataclasses are rebuilt, so a file that loads is one the GUI and the deck
writer can use. A value of the wrong type, an unknown ``_type`` or enum
member, a number that is NaN or infinite, a whole number beyond +-2**53
(the browser cannot carry it), a fraction in an integer field, or a
missing required field refuses the file with a :class:`ValueError` that
names the file and the field. An integer field written as a whole float
(``2020.0``, as the GUI's number boxes store it) reads as the integer.
Saving applies the same checks and repairs before anything is written, so
pyaermod never writes a file it would refuse to open. Files written
before the ``_type`` tags covered nested objects still load: an untagged
object is built as the field's own class. Unknown keys are ignored.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import shutil
import typing
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Type, Union

from ..input_generator import AERMODProject

SAVE_FORMAT_VERSION = 1

#: The largest whole number a project may hold. The browser's numbers are
#: doubles, exact to 2**53, and NiceGUI's JSON encoder refuses anything
#: beyond 64 bits, which freezes the page that shows it.
MAX_WHOLE_NUMBER = 2**53

#: The pathways every project has; ``null`` or a missing one reads as ``{}``.
_PATHWAYS = ("control", "sources", "receptors", "meteorology", "output")


# ---------------------------------------------------------------------
# Encoder
# ---------------------------------------------------------------------

def _encode(obj: Any) -> Any:
    """``obj`` as a tree of JSON values (see the module docstring)."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, Enum):
        return {"_enum": f"{type(obj).__name__}.{obj.name}"}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {f.name: _encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
        out["_type"] = type(obj).__name__
        return out
    if isinstance(obj, dict):
        if all(isinstance(k, str) for k in obj):
            return {k: _encode(v) for k, v in obj.items()}
        return {"_items": [[_encode(k), _encode(v)] for k, v in obj.items()]}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    try:  # numpy scalars when the user mixed numpy values into the project
        import numpy as np
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return [_encode(v) for v in obj.tolist()]
    except ImportError:  # pragma: no cover - numpy is a core dependency
        pass
    raise TypeError(f"cannot save a {type(obj).__name__} in a project file")


# ---------------------------------------------------------------------
# Decoder
# ---------------------------------------------------------------------

class _Types:
    """The dataclasses and enums a project file may name, and their field types."""

    def __init__(self) -> None:
        from .. import input_generator, pathways, receptors, sources, unparsed

        namespace: Dict[str, Any] = {}
        for module in (pathways, sources, receptors, unparsed, input_generator):
            namespace.update(vars(module))
        self.namespace = namespace
        self.dataclasses: Dict[str, type] = {}
        self.enums: Dict[str, Type[Enum]] = {}
        for value in namespace.values():
            if not isinstance(value, type):
                continue
            if dataclasses.is_dataclass(value):
                self.dataclasses.setdefault(value.__name__, value)
            elif issubclass(value, Enum):
                self.enums.setdefault(value.__name__, value)
        self._hints: Dict[type, Dict[str, Any]] = {}

    def hints(self, cls: type) -> Dict[str, Any]:
        """Resolved field types of ``cls``; an unresolvable one reads as Any."""
        if cls not in self._hints:
            try:
                hints = typing.get_type_hints(cls)
            except (NameError, AttributeError):
                # A name imported only for type checkers (ChemistryOptions'
                # SourceGroupDefinition); the model's own namespace has it.
                try:
                    hints = typing.get_type_hints(cls, localns=self.namespace)
                except (NameError, AttributeError):
                    hints = {}
            self._hints[cls] = hints
        return self._hints[cls]


_TYPES: Optional[_Types] = None


def _types() -> _Types:
    global _TYPES
    if _TYPES is None:
        _TYPES = _Types()
    return _TYPES


def _json_kind(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true/false"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return f"text {value!r}"
    if isinstance(value, list):
        return "a JSON list"
    if isinstance(value, dict):
        return "a JSON object"
    return type(value).__name__


def _expected(annotation: Any) -> str:
    """How the error message names what a field needs."""
    origin = typing.get_origin(annotation)
    if origin is Union:
        return " or ".join(_expected(a) for a in typing.get_args(annotation))
    if annotation is type(None):
        return "null"
    if annotation is bool:
        return "true/false"
    if annotation in (int, float):
        return "a number"
    if annotation in (str, Path):
        return "text"
    if origin in (list, tuple) or annotation in (list, tuple):
        return "a JSON list"
    if origin is dict or annotation is dict:
        return "a JSON object"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return f"a {annotation.__name__}"
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return "a JSON object"
    return str(annotation)


class _Decoder:
    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.types = _types()

    def fail(self, what: str, message: str) -> ValueError:
        return ValueError(f"{self.origin}: {what}{message}")

    def wrong_type(self, what: str, value: Any, annotation: Any) -> ValueError:
        return self.fail(what, f" must be {_expected(annotation)}, not {_json_kind(value)}")

    # -- values of a known type --------------------------------------
    def value(self, value: Any, annotation: Any, what: str) -> Any:
        if annotation is Any or annotation is object:
            return self.untyped(value, what)
        origin = typing.get_origin(annotation)
        args = typing.get_args(annotation)
        if origin is Union:
            return self.union(value, args, annotation, what)
        if annotation is type(None):
            if value is None:
                return None
            raise self.wrong_type(what, value, annotation)
        if origin is typing.Literal:
            if value in args:
                return value
            raise self.fail(what, f" must be one of {list(args)}, not {value!r}")
        if annotation is bool:
            if isinstance(value, bool):
                return value
            raise self.wrong_type(what, value, annotation)
        if annotation is int:
            if isinstance(value, float) and not isinstance(value, bool):
                # The GUI's number boxes store floats; the deck writer
                # formats integer fields with "d", which refuses a float.
                value = self.finite(value, what)
                if not value.is_integer():
                    raise self.fail(what, f" must be a whole number, not {value}")
                value = int(value)
            if isinstance(value, int) and not isinstance(value, bool):
                return self.finite(value, what)
            raise self.wrong_type(what, value, annotation)
        if annotation is float:
            # An int fills a float field unchanged (JSON writes 5.0 as 5 in
            # some tools).
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return self.finite(value, what)
            raise self.wrong_type(what, value, annotation)
        if annotation is str:
            if isinstance(value, str):
                return value
            raise self.wrong_type(what, value, annotation)
        if origin is list or annotation is list:
            if not isinstance(value, list):
                raise self.wrong_type(what, value, annotation)
            item_type = args[0] if args else Any
            return [self.value(v, item_type, f"{what}[{i}]") for i, v in enumerate(value)]
        if origin is tuple or annotation is tuple:
            return self.tuple_value(value, args, annotation, what)
        if origin is dict or annotation is dict:
            key_type, item_type = args if len(args) == 2 else (Any, Any)
            return self.dict_value(value, key_type, item_type, annotation, what)
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            return self.enum(value, annotation, what)
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            return self.dataclass_value(value, (annotation,), what)
        if annotation is Path:
            if isinstance(value, str):
                return Path(value)
            raise self.wrong_type(what, value, annotation)
        # A type the file format does not know how to check: keep the value.
        return self.untyped(value, what)

    def union(self, value: Any, members: Tuple[Any, ...], annotation: Any, what: str) -> Any:
        if value is None:
            if type(None) in members:
                return None
            raise self.wrong_type(what, value, annotation)
        present = [m for m in members if m is not type(None)]
        if len(present) == 1:
            # Optional[X]: X's own check says what is wrong, down to the item.
            return self.value(value, present[0], what)
        classes = tuple(m for m in present if isinstance(m, type) and dataclasses.is_dataclass(m))
        others = [m for m in present if m not in classes]
        if classes and not others:
            return self.dataclass_value(value, classes, what)  # dispatch on _type
        tagged_error = None
        for member in [*others, *classes]:
            try:
                return self.value(value, member, what)
            except ValueError as exc:
                if tagged_error is None and self._tag_matches(value, member):
                    tagged_error = exc
        if tagged_error is not None:
            raise tagged_error  # the member the tag names says what is wrong
        raise self.wrong_type(what, value, annotation)

    def finite(self, value: Any, what: str) -> Any:
        """``value``, unless it is a number the GUI cannot carry.

        That is a float AERMOD cannot use (NaN, +-Infinity), or a whole
        number beyond +-:data:`MAX_WHOLE_NUMBER`.
        """
        if isinstance(value, float) and not math.isfinite(value):
            raise self.fail(what, f" must be a finite number, not {value}")
        if (isinstance(value, int) and not isinstance(value, bool)
                and not -MAX_WHOLE_NUMBER <= value <= MAX_WHOLE_NUMBER):
            digits = len(str(abs(value)))
            shown = str(value) if digits <= 30 else f"a {digits}-digit number"
            raise self.fail(what, f" is too large: {shown} (the largest whole number "
                                  f"a project can hold is 2**53)")
        return value

    @staticmethod
    def _tag_matches(value: Any, member: Any) -> bool:
        """True if ``value`` is tagged as the kind of thing ``member`` is."""
        if not isinstance(value, dict) or not isinstance(member, type):
            return False
        if "_enum" in value:
            return issubclass(member, Enum)
        return "_type" in value and dataclasses.is_dataclass(member)

    def tuple_value(self, value: Any, args: Tuple[Any, ...], annotation: Any, what: str) -> tuple:
        if not isinstance(value, list):
            raise self.wrong_type(what, value, annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(self.value(v, args[0], f"{what}[{i}]") for i, v in enumerate(value))
        if args:
            if len(value) != len(args):
                raise self.fail(what, f" must have {len(args)} values, not {len(value)}")
            return tuple(self.value(v, t, f"{what}[{i}]")
                         for i, (v, t) in enumerate(zip(value, args, strict=True)))
        return tuple(self.untyped(v, f"{what}[{i}]") for i, v in enumerate(value))

    def dict_value(self, value: Any, key_type: Any, item_type: Any, annotation: Any, what: str) -> dict:
        if not isinstance(value, dict):
            raise self.wrong_type(what, value, annotation)
        if "_items" in value:
            pairs = value["_items"]
            if not isinstance(pairs, list) or not all(
                    isinstance(p, list) and len(p) == 2 for p in pairs):
                raise self.fail(what, " must list [key, value] pairs")
            items = [(self.key(k, key_type, what), self.value(v, item_type, f"{what}[{k!r}]"))
                     for k, v in pairs]
        else:
            items = [(self.key(k, key_type, what), self.value(v, item_type, f"{what}[{k!r}]"))
                     for k, v in value.items()]
        return dict(items)

    def key(self, key: Any, key_type: Any, what: str) -> Any:
        result = self._key(key, key_type, what)
        try:
            hash(result)
        except TypeError:
            raise self.fail(what, f" has a key that cannot be looked up: {_json_kind(key)}") from None
        return result

    def _key(self, key: Any, key_type: Any, what: str) -> Any:
        if key_type is int and isinstance(key, str):
            # A JSON object's keys are text; an int-keyed dict written as one.
            try:
                number = int(key)
            except ValueError:
                raise self.fail(what, f" has key {key!r}, not a whole number") from None
            return self.finite(number, f"{what} key")
        if key_type is Any or key_type is object:
            if isinstance(key, list):  # a tuple key, written as a list
                return tuple(self._key(k, Any, what) for k in key)
            return self.untyped(key, what)
        if isinstance(key, list) and (typing.get_origin(key_type) is tuple or key_type is tuple):
            return self.tuple_value(key, typing.get_args(key_type), key_type, f"{what} key")
        # Anything else is checked as the key type, which refuses a list
        # where the field wants a number, naming the field.
        return self.value(key, key_type, f"{what} key")

    def enum(self, value: Any, cls: Type[Enum], what: str) -> Enum:
        if isinstance(value, dict) and "_enum" in value:
            tag = value["_enum"]
            if not isinstance(tag, str) or tag.count(".") != 1:
                raise self.fail(what, f": {tag!r} is not an enum tag (EnumClass.MEMBER)")
            cls_name, member = tag.split(".")
            if cls_name != cls.__name__:
                raise self.fail(what, f" must be a {cls.__name__}, not a {cls_name}")
            if member not in cls.__members__:
                raise self.fail(what, f": unknown {cls.__name__} member {member!r}")
            return cls[member]
        if isinstance(value, str):
            try:
                return cls(value)   # the enum's value, as AERMOD spells it
            except ValueError:
                raise self.fail(what, f": unknown {cls.__name__} value {value!r}") from None
        raise self.wrong_type(what, value, cls)

    def dataclass_value(self, value: Any, classes: Tuple[type, ...], what: str) -> Any:
        if not isinstance(value, dict):
            raise self.fail(what, f" must be a JSON object, not {_json_kind(value)}")
        tag = value.get("_type")
        cls: Optional[type]
        if tag is None:
            if len(classes) != 1:
                raise self.fail(what, " has no _type saying which kind of object it is")
            cls = classes[0]
        else:
            cls = self.types.dataclasses.get(tag) if isinstance(tag, str) else None
            if cls is None or not issubclass(cls, classes):
                kinds = ", ".join(c.__name__ for c in classes)
                raise self.fail(what, f": unknown type {tag!r} (expected {kinds})")
        return self.build(cls, value, what)

    def build(self, cls: type, payload: dict, what: str) -> Any:
        hints = self.types.hints(cls)
        kwargs = {}
        missing = []
        for f in dataclasses.fields(cls):
            if not f.init:
                continue
            if f.name not in payload:
                if (f.default is dataclasses.MISSING
                        and f.default_factory is dataclasses.MISSING):
                    missing.append(f.name)
                continue
            kwargs[f.name] = self.value(payload[f.name], hints.get(f.name, Any),
                                        f"{what}.{f.name}")
        if missing:
            raise self.fail(what, f": missing required field {', '.join(map(repr, missing))}")
        try:
            return cls(**kwargs)
        except (TypeError, ValueError) as exc:  # the class's own checks
            raise self.fail(what, f": {exc}") from exc

    # -- values of no declared type ----------------------------------
    def untyped(self, value: Any, what: str) -> Any:
        if isinstance(value, list):
            return [self.untyped(v, f"{what}[{i}]") for i, v in enumerate(value)]
        if not isinstance(value, dict):
            return self.finite(value, what)
        if "_enum" in value:
            tag = value["_enum"]
            cls_name = tag.split(".")[0] if isinstance(tag, str) else None
            cls = self.types.enums.get(cls_name) if cls_name else None
            if cls is None:
                raise self.fail(what, f": unknown enum {tag!r}")
            return self.enum(value, cls, what)
        if "_type" in value:
            return self.dataclass_value(value, (object,), what)
        return self.dict_value(value, Any, Any, dict, what)


def _decode_project(project_raw: Any, origin: str) -> AERMODProject:
    decoder = _Decoder(origin)
    if not isinstance(project_raw, dict):
        raise decoder.fail("project", f" must be a JSON object, not {_json_kind(project_raw)}")
    payload = dict(project_raw)
    for name in _PATHWAYS:
        # Older files may leave a pathway out; its defaults stand in.
        if payload.get(name) is None:
            payload[name] = {}
    return decoder.build(AERMODProject, payload, "project")


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------

def check_project(project: AERMODProject, *, origin: str = "the project") -> AERMODProject:
    """Return a copy of ``project`` as :func:`project_from_json` would read it.

    The copy has every value checked against its field's type and repaired
    where the loader repairs it (``2020.0`` in an integer field becomes
    ``2020``). Raises :class:`ValueError` starting with ``origin`` and
    naming the field when the loader would refuse a value, and
    :class:`TypeError` for a value no project file can hold.
    """
    try:
        return _decode_project(_encode(project), origin)
    except RecursionError:
        raise ValueError(f"{origin}: nested too deeply") from None


def project_to_json(project: AERMODProject) -> str:
    """Return ``project`` as the JSON text :func:`save_project` writes.

    The project is written as :func:`check_project` reads it, so a file
    that cannot be opened again is never produced: :class:`ValueError`
    names the field holding a value :func:`project_from_json` would refuse
    (a missing number, text in a list of objects, NaN ...), and
    :class:`TypeError` means a value no project file can hold.
    """
    from .. import __version__

    tree = _encode(check_project(project, origin="cannot save the project"))
    payload = {
        "pyaermod_version": __version__,
        "save_format_version": SAVE_FORMAT_VERSION,
        "project": tree,
    }
    # allow_nan=False: the check above already refuses NaN with its field.
    return json.dumps(payload, indent=2, allow_nan=False)


def save_project(
    project: AERMODProject, path: Union[str, Path],
) -> Path:
    """Write ``project`` to ``path`` as JSON. Returns the path.

    Nothing is created when :func:`project_to_json` refuses the project.
    The file is written beside ``path`` and then moved over it, so a
    failed write leaves any earlier file at ``path`` whole.
    """
    out = Path(path)
    text = project_to_json(project)
    out.parent.mkdir(parents=True, exist_ok=True)
    # open(..., "x") rather than mkstemp: the file gets the umask's mode,
    # not 0600, and an existing file's mode is kept below.
    tmp = out.with_name(f".{out.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "x", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if out.exists():
            shutil.copymode(out, tmp)
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return out


def project_from_json(text: Union[str, bytes], *, origin: str = "<text>") -> AERMODProject:
    """Read an AERMODProject from JSON text written by :func:`project_to_json`.

    Tolerates older save formats by reading what's there and filling
    missing fields with dataclass defaults. Every problem with the text
    itself -- not UTF-8, invalid JSON, a document of the wrong shape, a
    value of the wrong type, a newer save format -- raises
    :class:`ValueError` whose message starts with ``origin`` (a file name,
    or ``"<text>"``).
    """
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{origin}: not a UTF-8 text file ({exc.reason} "
                             f"at byte {exc.start})") from None
    try:
        raw = json.loads(text)
    except ValueError as exc:
        # JSONDecodeError, or a number with more digits than Python reads.
        raise ValueError(f"{origin}: not valid JSON ({exc})") from exc
    except RecursionError:
        raise ValueError(f"{origin}: nested too deeply to be a project file") from None
    if not isinstance(raw, dict) or "project" not in raw:
        raise ValueError(f"{origin}: not a pyaermod project file")
    sfv = raw.get("save_format_version")
    if sfv is not None and (not isinstance(sfv, int) or isinstance(sfv, bool)):
        raise ValueError(f"{origin}: save_format_version={sfv!r} is not a number")
    if sfv is not None and sfv > SAVE_FORMAT_VERSION:
        raise ValueError(
            f"{origin}: save_format_version={sfv} is newer than this build "
            f"supports (max {SAVE_FORMAT_VERSION}). Upgrade pyaermod."
        )
    try:
        return _decode_project(raw["project"], origin)
    except RecursionError:
        raise ValueError(f"{origin}: nested too deeply to be a project file") from None


def load_project(path: Union[str, Path]) -> AERMODProject:
    """Read an AERMODProject from a JSON file written by :func:`save_project`."""
    return project_from_json(Path(path).read_bytes(), origin=str(path))


__all__ = [
    "MAX_WHOLE_NUMBER",
    "SAVE_FORMAT_VERSION",
    "check_project",
    "load_project",
    "project_from_json",
    "project_to_json",
    "save_project",
]

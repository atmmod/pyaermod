"""
The browser GUI's Python side: every GUI operation as JSON in, JSON out.

The browser GUI (``webapp/``, published under ``/app/`` of the documentation site)
runs pyaermod and AERMOD's WebAssembly build in Pyodide inside a Web
Worker. Its JavaScript calls exactly one function here, :func:`call`,
with an operation name and a JSON text of arguments, and gets a JSON text
back. Nothing here imports NiceGUI or needs a thread or a process, so the
module runs unchanged under CPython, which is where its tests run.

The project travels as the document :func:`pyaermod.gui_v2.project_io.project_to_json`
writes, so a file saved by the browser GUI opens in ``pyaermod-app`` and
the reverse. Every operation that takes a project reads it with the same
checks as opening a file, and every one that changes it returns the
document again.

Replies are ``{"ok": true, ...}`` or ``{"ok": false, "error": {"kind",
"message", "step"}}``; an exception never crosses into JavaScript.

Files (met files, AERMAP output, a deck and the files it names, AERMOD's
output) live in one working directory, :data:`WORK_DIR`: AERMOD runs
there and opens relative names from there. Uploaded file names are cut
to their last part, so nothing is written outside it.

Not for regulatory use: the AERMOD in the browser is EPA's source
compiled to WebAssembly by pyaermod, not EPA's executable.
"""

from __future__ import annotations

import base64
import csv
import dataclasses
import io
import json
import math
import shutil
import tempfile
import traceback
import typing
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import __version__, wasm_runner

#: What every page of the browser GUI says about the model it runs.
BANNER = ("AERMOD compiled to WebAssembly by pyaermod. Not EPA's executable; "
          "not for regulatory use.")

#: Where uploaded files are written and AERMOD runs. Under Pyodide a folder
#: of the in-memory file system; under CPython (tests, the dev bridge) a
#: temporary folder made on first use. Tests may set it.
WORK_DIR: Optional[Path] = Path("/home/pyodide/work") if wasm_runner.IS_EMSCRIPTEN else None

#: Builds the AERMOD runner for :func:`run`. None: AERMODRunner() (the
#: WebAssembly build under Pyodide, the ``aermod`` on PATH elsewhere).
#: Tests and the dev bridge put a runner that replays a recorded run here.
RUNNER_FACTORY: Optional[Callable[[], Any]] = None

#: At most this many rows of each summary table go to the page.
MAX_TABLE_ROWS = 500
#: At most this many concentration maps are drawn per run.
MAX_MAPS = 6

_TERRAIN_SUFFIXES = (".csv", ".txt")


class BrowserError(Exception):
    """A problem to show the user, on ``step`` when one applies."""

    def __init__(self, message: str, *, kind: str = "invalid", step: Optional[str] = None):
        super().__init__(message)
        self.kind = kind
        self.step = step


# ----------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------

def work_dir() -> Path:
    """The working directory, made when first needed."""
    global WORK_DIR
    if WORK_DIR is None:
        WORK_DIR = Path(tempfile.mkdtemp(prefix="pyaermod_browser_"))
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return WORK_DIR


def clean_name(name: str) -> str:
    """A file name cut to its last part: no folders, nothing outside :func:`work_dir`."""
    last = str(name or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    if last in ("", ".", ".."):
        raise BrowserError(f"{name!r} is not a file name", kind="file")
    return last


def put_file(name: str, data_b64: str) -> Dict[str, Any]:
    """Write an uploaded file into the working directory."""
    target = work_dir() / clean_name(name)
    data = base64.b64decode(data_b64)
    target.write_bytes(data)
    return {"name": target.name, "size": len(data)}


def list_files() -> Dict[str, Any]:
    """The files in the working directory, by name, with their sizes."""
    files = sorted((p for p in work_dir().iterdir() if p.is_file()), key=lambda p: p.name.lower())
    return {"files": [{"name": p.name, "size": p.stat().st_size} for p in files]}


def remove_file(name: str) -> Dict[str, Any]:
    (work_dir() / clean_name(name)).unlink(missing_ok=True)
    return list_files()


# ----------------------------------------------------------------------
# Projects as documents
# ----------------------------------------------------------------------

def _document(project: Any) -> Dict[str, Any]:
    from .gui_v2.project_io import project_to_json

    try:
        return json.loads(project_to_json(project))
    except (TypeError, ValueError) as exc:
        raise BrowserError(str(exc), kind="project") from exc


def _project(document: Any) -> Any:
    """The project in ``document`` (a project file's JSON, as a dict or text)."""
    from .gui_v2.project_io import project_from_json

    text = document if isinstance(document, str) else json.dumps(document)
    try:
        return project_from_json(text, origin="the project")
    except ValueError as exc:
        raise BrowserError(str(exc), kind="project", step=_step_named_by(str(exc))) from exc


def _step_named_by(message: str) -> Optional[str]:
    for part, step in (("project.control", "project"), ("project.sources", "sources"),
                       ("project.receptors", "receptors"), ("project.meteorology", "meteorology"),
                       ("project.output", "output")):
        if part in message:
            return step
    return None


def new_project() -> Dict[str, Any]:
    """The project New starts from, the same as ``pyaermod-app``'s."""
    from .gui_v2.state import _empty_project

    return {"document": _document(_empty_project())}


def load(text: str) -> Dict[str, Any]:
    """A project file's text, checked; the document as pyaermod writes it."""
    return {"document": _document(_project(text))}


def new_item(type_name: str) -> Dict[str, Any]:
    """A new source or receptor of ``type_name`` with the pip GUI's starting values."""
    from .gui_v2.pages.receptors import _RECEPTOR_TYPES, _new_receptor
    from .gui_v2.pages.sources import _SOURCE_TYPES, _new_source
    from .gui_v2.project_io import _encode

    if type_name in _SOURCE_TYPES:
        return {"item": _encode(_new_source(type_name))}
    if type_name in _RECEPTOR_TYPES:
        return {"item": _encode(_new_receptor(type_name))}
    raise BrowserError(f"unknown source or receptor type {type_name!r}")


# ----------------------------------------------------------------------
# The form schema
# ----------------------------------------------------------------------

#: Fields offered as a set of choices rather than free text.
def _choice_overrides() -> Dict[Tuple[str, str], List[str]]:
    from .gui_v2.pages.project import AVERAGING_PERIODS

    return {("ControlPathway", "averaging_periods"): list(AVERAGING_PERIODS)}


def _unwrap_optional(tp: Any) -> Tuple[Any, bool]:
    if typing.get_origin(tp) is typing.Union:
        args = tuple(a for a in typing.get_args(tp) if a is not type(None))
        if len(args) < len(typing.get_args(tp)):
            return (args[0] if len(args) == 1 else typing.Union[args]), True
    return tp, False


def _is_point_list(tp: Any) -> bool:
    """List[Tuple[float, float]] and the like: edited as "x, y" lines."""
    if typing.get_origin(tp) not in (list, typing.List):
        return False
    (item,) = typing.get_args(tp) or (None,)
    item, _ = _unwrap_optional(item)
    args = typing.get_args(item)
    return typing.get_origin(item) in (tuple, typing.Tuple) and len(args) in (2, 3) and all(
        a in (float, int) for a in args)


def _field_kind(tp: Any) -> Tuple[str, Dict[str, Any]]:
    extra: Dict[str, Any] = {}
    if typing.get_origin(tp) is typing.Union:
        members = typing.get_args(tp)
        enums = [m for m in members if isinstance(m, type) and issubclass(m, Enum)]
        # Union[str, PollutantType]: the enum's members, or a name AERMOD
        # knows that the enum does not list.
        if len(enums) == 1 and set(members) <= {str, enums[0]}:
            kind, extra = _field_kind(enums[0])
            extra["custom"] = str in members
            return kind, extra
        # Union[float, List[float]]: one value, or one per wind direction.
        if set(members) == {float, typing.List[float]}:
            return "numbers", extra
    if tp is bool:
        return "boolean", extra
    if tp is int:
        return "integer", extra
    if tp is float:
        return "number", extra
    if tp is str:
        return "string", extra
    if isinstance(tp, type) and issubclass(tp, Enum):
        extra["choices"] = [{"value": {"_enum": f"{tp.__name__}.{m.name}"}, "label": str(m.value)}
                            for m in tp]
        return "enum", extra
    if _is_point_list(tp):
        extra["width"] = len(typing.get_args(_unwrap_optional(typing.get_args(tp)[0])[0]))
        return "points", extra
    if typing.get_origin(tp) in (list, typing.List) and typing.get_args(tp) in ((str,), (float,),
                                                                              (int,)):
        extra["item"] = {str: "string", float: "number", int: "integer"}[typing.get_args(tp)[0]]
        return "list", extra
    return "json", extra


def class_schema(cls: type) -> Dict[str, Any]:
    """The fields of dataclass ``cls`` as the shell's forms draw them."""
    from ._fields import help_of, units_of
    from .gui_v2.project_io import _encode, _types

    hints = _types().hints(cls)
    overrides = _choice_overrides()
    fields = []
    for f in dataclasses.fields(cls):
        if not f.init or f.name.startswith("_"):
            continue
        tp, optional = _unwrap_optional(hints.get(f.name, Any))
        kind, extra = _field_kind(tp)
        if (cls.__name__, f.name) in overrides:
            kind, extra = "multichoice", {"choices": overrides[(cls.__name__, f.name)]}
        required = f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        default: Any = None
        if f.default is not dataclasses.MISSING:
            default = _encode(f.default)
        elif f.default_factory is not dataclasses.MISSING:
            default = _encode(f.default_factory())
        fields.append({
            "name": f.name,
            "label": f.name.replace("_", " ").capitalize(),
            "kind": kind,
            "optional": optional,
            "required": required,
            "units": units_of(f),
            "help": help_of(f),
            "default": default,
            **extra,
        })
    return {"name": cls.__name__, "doc": (cls.__doc__ or "").strip().split("\n")[0],
            "fields": fields}


def schema() -> Dict[str, Any]:
    """Everything the shell needs to draw its forms, with no project."""
    from .gui_v2.pages import meteorology, output
    from .gui_v2.pages.project import OUTPUT_OPTIONS, TERRAIN_CHOICES
    from .gui_v2.pages.receptors import _RECEPTOR_TYPES
    from .gui_v2.pages.sources import _SOURCE_TYPES
    from .gui_v2.steps import STEPS
    from .input_generator import ControlPathway, MeteorologyPathway, OutputPathway

    classes = {cls.__name__: class_schema(cls) for cls in (
        *_SOURCE_TYPES.values(), *_RECEPTOR_TYPES.values(),
        ControlPathway, MeteorologyPathway, OutputPathway)}
    return {
        "version": __version__,
        "banner": BANNER,
        "steps": [{"id": s.id, "label": s.label} for s in STEPS],
        "sources": list(_SOURCE_TYPES),
        "receptors": list(_RECEPTOR_TYPES),
        "classes": classes,
        "groups": {
            "project": [
                {"title": "Titles and pollutant",
                 "fields": ["title_one", "title_two", "pollutant_id"]},
                {"title": "Averaging periods", "fields": ["averaging_periods"]},
                {"title": "Model options",
                 "fields": ["terrain_type", *[name for name, _ in OUTPUT_OPTIONS]]},
            ],
            "meteorology": [{"title": t, "intro": i, "fields": list(f)}
                            for t, i, f in meteorology.GROUPS],
            "output": [
                {"title": "Tables", "fields": list(output.TABLE_FIELDS)},
                {"title": "Files", "fields": list(output.FILE_FIELDS)},
                {"title": "Files for the Results step", "fields": list(output.RESULTS_FIELDS)},
            ],
            "hidden": {"OutputPathway": list(output.HIDDEN_FIELDS)},
        },
        "terrain_labels": dict(TERRAIN_CHOICES),
        "limits": {"max_table_rows": MAX_TABLE_ROWS, "max_maps": MAX_MAPS},
    }


# ----------------------------------------------------------------------
# Review: what blocks a run
# ----------------------------------------------------------------------

def _session(project: Any) -> Any:
    from .gui_v2.session import Session

    session = Session(project)
    session.run_options.working_dir = str(work_dir())
    return session


def _have_aermod() -> bool:
    if RUNNER_FACTORY is not None:
        return True
    if wasm_runner.IS_EMSCRIPTEN:
        try:
            wasm_runner.find_wasm_aermod()
        except FileNotFoundError:
            return False
        return True
    return shutil.which("aermod") is not None


NO_WASM = ("AERMOD's WebAssembly build did not load. Reload the page; if it still "
           "fails, install the GUI with pip (see the GUI guide).")


def _items(items: List[Any]) -> List[Dict[str, Any]]:
    from .gui_v2.readiness import NO_BINARY

    return [{"step": i.step, "title": i.title, "links": i.links,
             "problems": [NO_WASM if p == NO_BINARY else p for p in i.problems]}
            for i in items]


#: The step that names each kind of input file, by its deck pathway.
_INPUT_STEPS = {"ME": "meteorology", "SO": "sources", "RE": "receptors", "CO": "project"}


def _not_uploaded(project: Any) -> List[Dict[str, Any]]:
    """Checklist items for input files that are not in the working directory.

    In the browser the working directory is the only place AERMOD can open
    a file from, so a file the deck names and nobody uploaded blocks the
    run (the pip GUI leaves that to AERMOD, which may find it on disk).
    """
    from .gui_v2.readiness import STEP_TITLES
    from .input_reader import input_files
    from .pathways import unquote_path

    items: Dict[str, Dict[str, Any]] = {}
    for ref in input_files(project):
        name = unquote_path(ref.path)
        if (work_dir() / clean_name(name)).is_file() and clean_name(name) == name:
            continue
        step = _INPUT_STEPS.get(ref.keyword.split()[0], "project")
        item = items.setdefault(step, {"step": step, "title": STEP_TITLES.get(step, step),
                                       "links": [step], "problems": []})
        item["problems"].append(f"{name} ({ref.keyword}) has not been uploaded: add it "
                                "on the Meteorology step's file list, or pick a sample")
    return list(items.values())


def _merge(found: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from .gui_v2.readiness import STEP_IDS

    by_step = {i["step"]: i for i in found}
    for item in extra:
        if item["step"] in by_step:
            by_step[item["step"]]["problems"].extend(
                p for p in item["problems"] if p not in by_step[item["step"]]["problems"])
        else:
            by_step[item["step"]] = item
    return sorted(by_step.values(), key=lambda i: STEP_IDS.index(i["step"])
                  if i["step"] in STEP_IDS else len(STEP_IDS))


def _review(project: Any) -> Dict[str, Any]:
    from .gui_v2.readiness import review

    found = review(_session(project), have_binary=_have_aermod())
    blocking = _merge(_items(found.blocking), _not_uploaded(project))
    return {"ready": not blocking, "blocking": blocking,
            "warnings": _items(found.warnings), "deck": found.deck,
            "met_summary": found.met_summary}


def check(document: Any) -> Dict[str, Any]:
    """The Review & Run checklist of ``document``'s project, and its deck.

    The pip GUI's checklist (:func:`pyaermod.gui_v2.readiness.review`),
    plus every input file the deck names that has not been uploaded.
    """
    return _review(_project(document))


def deck(document: Any) -> Dict[str, Any]:
    """The AERMOD deck ``document``'s project is written as."""
    from .gui_v2.session import DeckError

    try:
        return {"deck": _session(_project(document)).deck_text()}
    except DeckError as exc:
        raise BrowserError(str(exc), kind="deck") from exc


def plan_view(document: Any) -> Dict[str, Any]:
    """The plan view of sources and receptors, as SVG text."""
    from .gui_v2.plan_view import plan_view_svg

    return {"svg": plan_view_svg(_project(document))}


# ----------------------------------------------------------------------
# Decks and terrain
# ----------------------------------------------------------------------

def import_deck(name: str, text: str) -> Dict[str, Any]:
    """Read an AERMOD deck as a project.

    Every file AERMOD would read is looked for by its name alone in the
    working directory, where uploads go: ``../meteorology/a.sfc`` becomes
    ``a.sfc``, and the reply lists each name changed. A file AERMOD would
    write must stay in the working directory: a deck whose outputs reach
    outside it is refused (:func:`pyaermod.input_reader.read_aermod_input`'s
    sandbox). Upload the files a deck names before or after importing it;
    ``missing_files`` lists those still to come.
    """
    from .input_reader import (
        PathTraversalError,
        _input_file_slots,
        _validate_paths_within,
        read_aermod_input,
    )
    from .pathways import unquote_path

    # Read from a scratch folder and not kept: the deck becomes the project,
    # and a file left as aermod.inp (the name AERMOD reads) would block runs.
    scratch = Path(tempfile.mkdtemp(prefix="import_", dir=work_dir()))
    path = scratch / clean_name(name or "deck.inp")
    try:
        path.write_text(text, encoding="utf-8")
        project = read_aermod_input(path)
    except (ValueError, UnicodeDecodeError) as exc:
        raise BrowserError(f"The deck could not be read: {exc}", kind="deck",
                           step="project") from exc
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    renamed = []
    for ref, set_path in _input_file_slots(project):
        written = unquote_path(ref.path)
        flat = clean_name(written)
        if flat != written:
            set_path(flat)
            renamed.append({"keyword": ref.keyword, "from": written, "to": flat})
    try:
        _validate_paths_within(project, work_dir())
    except PathTraversalError as exc:
        raise BrowserError(f"The deck has AERMOD write files outside its own folder, which "
                           f"the browser cannot give it: {exc}", kind="deck",
                           step="project") from exc
    missing = sorted({clean_name(unquote_path(ref.path))
                      for ref, _set in _input_file_slots(project)
                      if not (work_dir() / clean_name(unquote_path(ref.path))).is_file()})
    unparsed = [f"{ln.pathway} {ln.keyword} (line {ln.lineno})" for ln in project.unparsed_lines]
    return {"document": _document(project), "missing_files": missing, "renamed": renamed,
            "kept_verbatim": unparsed}


def _terrain_frame(path: Path) -> Tuple[str, Any]:
    """("receptors" | "sources" | "csv", DataFrame) for an uploaded terrain file."""
    import pandas as pd

    from .terrain import AERMAPOutputParser

    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in _TERRAIN_SUFFIXES and "LOCATION" not in text.upper() \
            and "ELEV" not in text.upper().split():
        rows = []
        reader = csv.reader(io.StringIO(text))
        for i, row in enumerate(reader, start=1):
            cells = [c.strip() for c in row if c.strip()]
            if not cells or cells[0].startswith("#"):
                continue
            try:
                values = [float(c) for c in cells]
            except ValueError:
                if i == 1:
                    continue          # a header row
                raise BrowserError(f"{path.name} line {i}: expected numbers x, y, "
                                   f"elevation[, hill height]", kind="terrain") from None
            if len(values) not in (3, 4):
                raise BrowserError(f"{path.name} line {i}: expected x, y, elevation"
                                   f"[, hill height]", kind="terrain")
            rows.append({"x": values[0], "y": values[1], "zelev": values[2],
                         "zhill": values[3] if len(values) == 4 else values[2]})
        return "csv", pd.DataFrame(rows, columns=["x", "y", "zelev", "zhill"])
    if any(line.split()[:2] in (["SO", "LOCATION"],) or line.split()[:1] == ["LOCATION"]
           for line in text.splitlines() if line.split()):
        return "sources", AERMAPOutputParser.parse_source_output(path)
    return "receptors", AERMAPOutputParser.parse_receptor_output(path)


def apply_terrain(document: Any, name: str) -> Dict[str, Any]:
    """Set elevations (and hill heights) from an uploaded file in the working directory.

    The file is AERMAP's receptor output, AERMAP's source output, or a CSV
    of ``x, y, elevation[, hill height]`` (hill height defaults to the
    elevation), matched to discrete receptors and Cartesian grid points
    within 0.5 m. Returns the changed document and what was matched.
    """
    from .pathways import TerrainType
    from .terrain import TerrainProcessor

    path = work_dir() / clean_name(name)
    if not path.is_file():
        raise BrowserError(f"{name} has not been uploaded", kind="terrain", step="receptors")
    project = _project(document)
    try:
        kind, frame = _terrain_frame(path)
    except BrowserError:
        raise
    except Exception as exc:
        raise BrowserError(f"{path.name} could not be read as AERMAP output or as a CSV "
                           f"of x, y, elevation: {exc}", kind="terrain",
                           step="receptors") from exc
    if frame.empty:
        raise BrowserError(f"{path.name} holds no elevations", kind="terrain", step="receptors")

    tp = TerrainProcessor()
    before = _document(project)
    if kind == "sources":
        tp._update_source_elevations(project, frame)
    else:
        tp._update_receptor_elevations(project, frame)
        tp._update_grid_receptor_elevations(project, frame)
        tp._update_polar_grid_elevations(project, frame)
    after = _document(project)
    notes = []
    if after == before:
        notes.append(f"No {'source' if kind == 'sources' else 'receptor'} in the project "
                     f"matched {path.name}: check the coordinates or network names.")
    if project.control.terrain_type == TerrainType.FLAT:
        notes.append("The project's terrain is Flat, so AERMOD ignores elevations: choose "
                     "Elevated on the Project step.")
    return {"document": after, "kind": kind, "rows": len(frame), "notes": notes}


# ----------------------------------------------------------------------
# Running AERMOD and its results
# ----------------------------------------------------------------------

def _runner() -> Any:
    if RUNNER_FACTORY is not None:
        return RUNNER_FACTORY()
    from .runner import AERMODRunner

    return AERMODRunner(log_level="WARNING")


def run(document: Any) -> Dict[str, Any]:
    """Run AERMOD on ``document``'s project in the working directory; return its results.

    Refused (nothing run) while the checklist has items. The run is
    synchronous: under Pyodide it holds the worker until AERMOD ends, and
    the page cancels it by ending the worker.
    """
    from .gui_v2.pages.run import message_counts_text, run_status_text
    from .gui_v2.run_results import view_of

    project = _project(document)
    found = _review(project)
    if not found["ready"]:
        first = found["blocking"][0]
        raise BrowserError(f"Not ready to run: {first['title']}: {first['problems'][0]}",
                           kind="not_ready", step=first["step"])
    session = _session(project)
    record = session.start_run(working_dir=work_dir(), background=False, runner=_runner(),
                               timeout=24 * 3600)
    result = record.result
    messages = []
    if result is not None:
        messages = [{"severity": m.severity, "code": m.code, "pathway": m.pathway,
                     "module": m.module, "text": m.text, "detail": m.detail}
                    for m in (result.messages or [])]
    reply: Dict[str, Any] = {
        "status": record.status,
        "status_text": run_status_text(record),
        "counts_text": message_counts_text(record),
        "messages": messages,
        "seconds": result.runtime_seconds if result is not None else None,
    }
    reply["results"] = _results(view_of(record))
    return reply


def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (int, str, bool)):
        return value
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return str(value)


def _maxima(tables: List[Any]) -> List[Dict[str, Any]]:
    from .gui_v2.pages.results import _UNITS
    from .gui_v2.run_results import period_label, table_qualifier

    rows = []
    for table in tables:
        top = table.max_row or {}
        rows.append({
            "period": period_label(table.averaging_period),
            "qualifier": table_qualifier(table.title),
            "value": str(top.get("value_text") or table.max_value),
            "flag": top.get("flag") or "",
            "units": _UNITS.get(table.units, table.units),
            "x": _cell(table.max_location[0]),
            "y": _cell(table.max_location[1]),
            "group": top.get("group") or "",
            "date": str(top.get("date") or ""),
            "table": table.title or "",
            "output_type": table.output_type,
        })
    return rows


def _tables(tables: List[Any]) -> List[Dict[str, Any]]:
    from .gui_v2.pages.results import _OUTPUT_TYPES, _UNITS
    from .gui_v2.run_results import period_label

    out = []
    for table in tables:
        records = table.data.to_dict("records")
        kind = _OUTPUT_TYPES.get(table.output_type, table.output_type)
        out.append({
            "name": f"{kind}, {period_label(table.averaging_period)}: {table.title or ''}",
            "units": _UNITS.get(table.units, table.units),
            "total_rows": len(records),
            "rows": [{
                "group": r.get("group") or "",
                "rank": _cell(r.get("rank")),
                "value": str(r.get("value_text") or r.get("concentration")),
                "flag": r.get("flag") or "",
                "date": str(r.get("date") or ""),
                "x": _cell(r.get("x")),
                "y": _cell(r.get("y")),
                "network": r.get("grid_id") or "",
            } for r in records[:MAX_TABLE_ROWS]],
        })
    return out


def _results(view: Any) -> Dict[str, Any]:
    from .gui_v2.pages.results import _UNITS
    from .gui_v2.results_map import concentration_map_png

    out: Dict[str, Any] = {
        "succeeded": view.succeeded, "ran": view.ran, "headline": view.headline,
        "detail": view.detail, "fatal": list(view.fatal), "notes": list(view.notes),
        "files": [{"name": f.name, "label": f.label, "size": f.size} for f in view.files],
        "maxima": [], "deposition": [], "naaqs": [], "tables": [], "maps": [],
    }
    if not view.succeeded or view.results is None:
        return out
    conc, dep = view.concentration_tables(), view.deposition_tables()
    out["maxima"] = _maxima(conc)
    out["deposition"] = _maxima(dep)
    out["tables"] = _tables(conc + dep)
    out["naaqs"] = [{
        "standard": c.label, "level": c.level_text,
        "value": None if c.value is None else float(c.value),
        "x": None if c.location is None else _cell(c.location[0]),
        "y": None if c.location is None else _cell(c.location[1]),
        "basis": c.basis, "verdict": c.verdict, "how": c.how,
    } for c in view.naaqs]
    sources = tuple((s.source_id, float(s.x_coord), float(s.y_coord))
                    for s in view.results.sources)
    for plot in view.plots[:MAX_MAPS]:
        units = view.plot_units(plot)
        units = _UNITS.get(units, units) if units else (
            "µg/m³" if plot.output_type == "CONC" else "AERMOD's deposition units")
        try:
            png = concentration_map_png(plot, units=units, sources=sources)
        except Exception as exc:  # a field matplotlib cannot contour
            out["notes"].append(f"No map of {plot.file.name}: {exc}")
            continue
        out["maps"].append({"title": plot.title, "file": plot.file.name,
                            "src": "data:image/png;base64," + base64.b64encode(png).decode()})
    return out


def get_file(name: str) -> Dict[str, Any]:
    """A file of the working directory, for download, as base64."""
    path = work_dir() / clean_name(name)
    if not path.is_file():
        raise BrowserError(f"{name} does not exist", kind="file")
    return {"name": path.name, "data_b64": base64.b64encode(path.read_bytes()).decode("ascii")}


# ----------------------------------------------------------------------
# The one entry point JavaScript calls
# ----------------------------------------------------------------------

_OPERATIONS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "schema": schema,
    "new_project": new_project,
    "load": load,
    "new_item": new_item,
    "check": check,
    "deck": deck,
    "plan_view": plan_view,
    "import_deck": import_deck,
    "apply_terrain": apply_terrain,
    "run": run,
    "put_file": put_file,
    "list_files": list_files,
    "remove_file": remove_file,
    "get_file": get_file,
}


def _finite(value: Any) -> Any:
    """``value`` with every NaN or infinity as None: JSON has neither."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def call(operation: str, arguments: str = "{}") -> str:
    """Run ``operation`` with keyword arguments from the JSON text ``arguments``.

    Returns JSON text: the operation's reply with ``"ok": true``, or
    ``{"ok": false, "error": {"kind", "message", "step"}}``.
    """
    try:
        fn = _OPERATIONS.get(operation)
        if fn is None:
            raise BrowserError(f"unknown operation {operation!r}", kind="internal")
        kwargs = json.loads(arguments or "{}")
        if not isinstance(kwargs, dict):
            raise BrowserError("arguments must be a JSON object", kind="internal")
        reply = fn(**kwargs)
        return json.dumps({"ok": True, **_finite(reply)}, allow_nan=False)
    except BrowserError as exc:
        error = {"kind": exc.kind, "message": str(exc), "step": exc.step}
    except TypeError as exc:
        error = {"kind": "internal", "message": f"{operation}: {exc}", "step": None}
    except Exception as exc:  # a bug: say what it was, and keep the page alive
        error = {"kind": "internal", "message": f"{type(exc).__name__}: {exc}",
                 "step": None, "traceback": traceback.format_exc(limit=8)}
    return json.dumps({"ok": False, "error": error})


__all__ = ["BANNER", "MAX_MAPS", "MAX_TABLE_ROWS", "BrowserError", "apply_terrain", "call",
           "check", "class_schema", "clean_name", "deck", "get_file", "import_deck",
           "list_files", "load", "new_item", "new_project", "plan_view", "put_file",
           "remove_file", "run", "schema", "work_dir"]

"""
PyAERMOD ensembles: run a designed set of AERMOD runs and collect them.

A *design* is a list of rows, each a mapping of factor names to values
(``{"diameter_um": 10.0, "met": "COR"}``). :func:`run_design` builds one
AERMOD project per row with a function the caller supplies, runs every
project in its own directory, and records each run in a manifest, so
that an interrupted design picks up where it stopped when it is run
again. :func:`collect_plotfiles` reads the PLOTFILEs of the finished runs
into one table.

Each run is known by its **run ID**, the SHA-256 of the canonical JSON
(:func:`canonical_json`) of::

    {"binary_sha256": ..., "factors": {...},
     "input_files_sha256": {"HOUREMIS": ..., ...},
     "met_sha256": {"profile": ..., "surface": ...},
     "schema_version": SCHEMA_VERSION}

that is, of the row's factors, the SHA-256 of the AERMOD binary, the
SHA-256 of the surface and profile met files and of every other file
the deck has AERMOD read (``HOUREMIS``, an hourly ``BACKGRND`` file,
``OZONEFIL``, ``NOX_FILE``, ``INITFILE``, the ``MULTYEAR`` initial file,
``INCLUDED``; see :func:`run_design`), and the version of this scheme.
The ID does not depend on file paths or on when the run was made. A new
binary or an edited met or emission file makes a new run, in a new
directory; the old one is kept, and ``root/design.json`` names the runs
of the latest call, which :func:`collect_plotfiles` reads by default.

Layout under ``root``::

    root/
      manifest.json         one entry per run ID (EnsembleManifest)
      manifest.csv          the same, one row per run
      design.json           the run IDs of the latest run_design call
      runs/<run ID>/
        run.inp             the deck
        factors.json        what the run ID was computed from
        <surface>, <profile>, <other input files>
                            links to the files the deck reads (copies
                            where links cannot be made)
        run.out, run.err, run.sum, PLOTFILEs, ...

Why one directory per run: AERMOD reads ``aermod.inp`` and writes its
output files relative to its working directory, and the runner locks
that directory for the length of a run
(:meth:`pyaermod.runner.AERMODRunner.run`), so decks sharing a directory
run one after another whatever ``n_workers`` is, and decks naming the
same output file overwrite each other's results. :func:`run_design`
therefore rewrites every output file name the deck gives (PLOTFILE,
POSTFILE, SUMMFILE, MAXIFILE, RANKFILE, ERRORFIL, DEBUGOPT, ..., also in
the lines :mod:`pyaermod.input_reader` keeps verbatim) to its bare file
name inside the run's directory.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import enum
import hashlib
import json
import logging
import math
import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path, PurePath
from typing import Any, ClassVar, Dict, List, Optional, Tuple, Type, Union

from .pathways import DEBUG_OPTIONS
from .runner import AERMODRunner, AERMODRunResult, _batch_worker
from .runner_utils import ProgressReporter, RunManifest, RunManifestEntry, _output_is_valid

logger = logging.getLogger(__name__)

#: Version of the run-ID scheme and of the manifest entry. It is part of
#: every run ID, so changing what goes into an ID means raising it.
#: 2: the ID also hashes the input files other than the met files.
SCHEMA_VERSION = 2

#: The deck's file name in each run directory.
DECK_NAME = "run.inp"
#: The directory under ``root`` that holds one directory per run.
RUNS_DIR = "runs"
#: The manifest's file name under ``root``.
MANIFEST_NAME = "manifest.json"
#: The file in each run directory recording what its run ID hashes.
FACTORS_NAME = "factors.json"
#: The file under ``root`` naming the runs of the latest run_design call.
DESIGN_NAME = "design.json"

# AERMOD keeps a runstream field in CHARACTER*200 (ILEN_FLD in
# modules.f) and refuses a longer file name with E291, "Filename
# specified is too long. Maximum length = 200", followed by E500 when
# the file cannot be opened (checked against v26135 with SURFFILE paths
# of 199, 200, 201 and 230 characters).
MAX_FILENAME_LENGTH = 200

# The columns DesignResult.to_dataframe() adds to the factors.
_RESERVED_COLUMNS = frozenset({
    "run_id", "status", "skipped", "runtime_seconds", "warning_count",
    "run_dir", "error_message",
})

# Files the runner and AERMOD keep in a run directory, which no output
# or met file may be named: the deck, factors.json, the runner's
# aermod.inp link and lock, AERMOD's outputs as the runner renames them,
# and AERMOD's captured stdout and stderr.
_RESERVED_FILES = frozenset({
    DECK_NAME, FACTORS_NAME, "aermod.inp", "aermod.out", "aermod.err", "aermod.sum",
    "run.out", "run.err", "run.sum", "run.subproc.stdout", "run.subproc.stderr",
    ".pyaermod.lock", ".pyaermod-aermod-inp.sha256",
})

# Outputs a finished run must still have for resume to skip it. AERMOD
# opens these at setup (ouset.f), so a successful run always leaves them.
# DEBUGOPT: the debug files a successful run wrote (see _drop_unwritten).
_REQUIRED_OUTPUTS = ("PLOTFILE", "POSTFILE", "DEBUGOPT")

# Outputs AERMOD may leave unwritten in a successful run: coset.f opens
# a named debug file only when its option applies (PRIME without a
# building, AREA without an area-type source) and sends MODEL's output
# to DEPOS.DBG when DEPOS is not followed by MODEL (checked on v26135).
_MAYBE_UNWRITTEN = ("DEBUGOPT",)

# The met files' roles in the run ID, by the keyword that names them.
_MET_ROLES = {"SURFFILE": "surface", "PROFFILE": "profile"}


def _describe_input(keyword: str) -> str:
    return f"{_MET_ROLES[keyword]} met file" if keyword in _MET_ROLES else f"{keyword} file"

_VERSION_BANNER = re.compile(r"\*\*\*\s*AERMOD\s*-\s*VERSION\s+(\S+)\s*\*\*\*")


# ---------------------------------------------------------------------------
# Run IDs
# ---------------------------------------------------------------------------

def _canonical(value: Any) -> Any:
    """``value`` as plain JSON types, the same way every time."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"a run ID cannot hold the non-finite number {value!r}")
        return float(value)
    if isinstance(value, enum.Enum):
        return _canonical(value.value)
    if isinstance(value, PurePath):
        return value.as_posix()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        out = {"_type": type(value).__name__}
        for f in dataclasses.fields(value):
            out[f.name] = _canonical(getattr(value, f.name))
        return out
    if isinstance(value, Mapping):
        out = {}
        for k, v in value.items():
            if not isinstance(k, str):
                raise TypeError(
                    f"a run ID needs string keys; got {k!r} ({type(k).__name__})"
                )
            out[k] = _canonical(v)
        return out
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, (set, frozenset)):
        items = [_canonical(v) for v in value]
        return sorted(items, key=lambda v: json.dumps(v, sort_keys=True))
    # NumPy scalars and arrays, without importing NumPy here.
    item = getattr(value, "item", None)
    tolist = getattr(value, "tolist", None)
    ndim = getattr(value, "ndim", None)
    if callable(tolist) and ndim:
        return _canonical(tolist())
    if callable(item):
        return _canonical(item())
    raise TypeError(
        f"{type(value).__name__} cannot be written as JSON for a run ID; use "
        "numbers, strings, booleans, None, lists, dicts with string keys, "
        "enums or dataclasses of those"
    )


def canonical_json(value: Any) -> str:
    """The canonical JSON text of ``value``, from which run IDs are hashed.

    Keys are sorted, there is no whitespace, and text is UTF-8 rather
    than ``\\u`` escapes. A float is written as Python's shortest
    round-trip form, so ``1.0`` and ``1`` are different factors. An enum
    is written as its value, a path as its POSIX form, a dataclass as a
    dict of its fields with ``"_type"`` set to its class name, and a set
    as a sorted list. NaN, infinities, dicts with non-string keys and any
    other type raise, instead of being written in a form that could
    change between runs.
    """
    return json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )


def file_sha256(path: Union[str, Path], chunk_size: int = 1 << 20) -> str:
    """The SHA-256 of a file's bytes, as 64 lower-case hex digits."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk_size), b""):
            h.update(block)
    return h.hexdigest()


def run_id_payload(
    factors: Mapping[str, Any],
    binary_sha256: str,
    met_sha256: Mapping[str, str],
    input_files_sha256: Optional[Mapping[str, str]] = None,
    schema_version: int = SCHEMA_VERSION,
) -> Dict[str, Any]:
    """What a run ID is the hash of (see :func:`run_id`)."""
    return {
        "binary_sha256": binary_sha256,
        "factors": dict(factors),
        "input_files_sha256": dict(input_files_sha256 or {}),
        "met_sha256": dict(met_sha256),
        "schema_version": schema_version,
    }


def run_id(
    factors: Mapping[str, Any],
    binary_sha256: str,
    met_sha256: Mapping[str, str],
    input_files_sha256: Optional[Mapping[str, str]] = None,
    schema_version: int = SCHEMA_VERSION,
) -> str:
    """The run ID: SHA-256 of the canonical JSON of the factors and versions.

    ``met_sha256`` maps each met file's role (``"surface"``,
    ``"profile"``) to the SHA-256 of its bytes, and
    ``input_files_sha256`` does the same for the other files the deck
    reads, whose roles are their keywords (``"HOUREMIS"``, and
    ``"HOUREMIS.2"`` for a second, different file).
    """
    payload = run_id_payload(factors, binary_sha256, met_sha256, input_files_sha256,
                             schema_version)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Output file names
# ---------------------------------------------------------------------------

class _Slot:
    """One file name a deck gives, as a field of the project model."""

    def __init__(self, keyword: str, obj: Any, attr: Any):
        self.keyword = keyword
        self.obj = obj
        self.attr = attr  # attribute name, or an index into a list of tuples

    def get(self) -> Optional[str]:
        if isinstance(self.attr, int):
            return self.obj[self.attr][2]
        return getattr(self.obj, self.attr)

    def set(self, name: str) -> None:
        if isinstance(self.attr, int):
            row = list(self.obj[self.attr])
            row[2] = name
            self.obj[self.attr] = tuple(row)
        else:
            setattr(self.obj, self.attr, name)


class _ItemSlot:
    """One file name that is an item of a list of strings
    (``ControlPathway.debug_options``)."""

    def __init__(self, keyword: str, items: List[str], index: int):
        self.keyword = keyword
        self.items = items
        self.index = index

    def get(self) -> Optional[str]:
        return self.items[self.index]

    def set(self, name: str) -> None:
        self.items[self.index] = name


class _FieldSlot:
    """One file name in a line the reader kept verbatim (an UnparsedLine)."""

    def __init__(self, keyword: str, line: Any, index: int):
        self.keyword = keyword
        self.line = line
        self.index = index

    def get(self) -> Optional[str]:
        return self.line.fields[self.index]

    def set(self, name: str) -> None:
        self.line.fields[self.index] = name


# Where the file names sit in a line the reader keeps verbatim
# (AERMODProject.unparsed_lines): (pathway, keyword) -> the indexes into
# UnparsedLine.fields, the data fields after the keyword, of the names.
# "*" matches any pathway. From the RUNST1(LOCB(n):LOCE(n)) reads of
# v26135's setup routines, n - 3 being the index here: ouset.f OUPLOT,
# PERPLT, OUPOST, PERPST, OUMXFL, OURANK, OUTOXX, OUSEAS, OUEVAL,
# OUSUMM, OUMAXDLY, OUMXDLY_BYYR, OUMAXD_CONT; coset.f ERRFIL, EVNTFL,
# SAVEFL, INITFL, MYEAR, DEBOPT, OZONEFIL, NOXFILE; soset.f HREMIS,
# BACKGRND; setup.f INCLUDED.
_FieldRule = Callable[[List[str]], List[int]]


def _first_is(fields: List[str], *words: str) -> bool:
    return bool(fields) and fields[0].upper() in words


# DEBUGOPT's options (coset.f DEBOPT, DEBUGOPT_ARRAY); any other field
# is the file name of the option before it.
_DEBUG_OPTIONS = frozenset(DEBUG_OPTIONS)

_UNPARSED_OUTPUTS: Dict[Tuple[str, str], _FieldRule] = {
    # PLOTFILE PERIOD|ANNUAL grp file [unit]; PLOTFILE ave grp rank file [unit]
    ("OU", "PLOTFILE"): lambda f: [2] if _first_is(f, "PERIOD", "ANNUAL") else [3],
    ("OU", "POSTFILE"): lambda f: [3],          # ave grp format file [unit]
    ("OU", "MAXIFILE"): lambda f: [3],          # ave grp thresh file [unit]
    ("OU", "RANKFILE"): lambda f: [2],          # ave nval file [unit]
    ("OU", "TOXXFILE"): lambda f: [2],          # ave cutoff file [unit]
    ("OU", "SEASONHR"): lambda f: [1],          # grp file [unit]
    ("OU", "EVALFILE"): lambda f: [1],          # srcid file [unit]
    ("OU", "SUMMFILE"): lambda f: [0],
    ("OU", "MAXDAILY"): lambda f: [1],          # grp file [unit]
    ("OU", "MXDYBYYR"): lambda f: [1],
    # MAXDCONT grp rank1 THRESH value file [unit] | grp rank1 rank2 file [unit]
    ("OU", "MAXDCONT"): lambda f: [4] if len(f) > 2 and f[2].upper() == "THRESH" else [3],
    ("CO", "ERRORFIL"): lambda f: [0],          # [file]; bare: ERRORS.LST
    ("CO", "EVENTFIL"): lambda f: [0],          # [file [option]]
    ("CO", "SAVEFILE"): lambda f: [0, 2],       # [file [dayinc [file2]]]
    ("CO", "MULTYEAR"): lambda f: [1] if _first_is(f, "H6H") else [0],
    ("CO", "DEBUGOPT"): lambda f: [i for i, t in enumerate(f) if t.upper() not in _DEBUG_OPTIONS],
}

_UNPARSED_INPUTS: Dict[Tuple[str, str], _FieldRule] = {
    ("SO", "HOUREMIS"): lambda f: [0],          # file srcid(s)
    # BACKGRND [SECTn] HOURLY file [format]
    ("SO", "BACKGRND"): lambda f: [i + 1 for i, t in enumerate(f) if t.upper() == "HOURLY"],
    # OZONEFIL [SECTn] file [units [format]]; NOX_FILE likewise
    ("CO", "OZONEFIL"): lambda f: [1] if f and f[0].upper().startswith("SECT") else [0],
    ("CO", "NOX_FILE"): lambda f: [1] if f and f[0].upper().startswith("SECT") else [0],
    ("CO", "INITFILE"): lambda f: [0],          # [file]; bare: SAVE.FIL
    ("CO", "MULTYEAR"): lambda f: [2] if _first_is(f, "H6H") else [1],
    ("*", "INCLUDED"): lambda f: [0],
}


def _unparsed_slots(project: Any, rules: Mapping[Tuple[str, str], _FieldRule]
                    ) -> Iterator[_FieldSlot]:
    for line in getattr(project, "unparsed_lines", None) or []:
        keyword = line.keyword.upper()
        rule = rules.get((line.pathway.upper(), keyword)) or rules.get(("*", keyword))
        if rule is None:
            continue
        for index in rule(line.fields):
            if index < len(line.fields):
                yield _FieldSlot(keyword, line, index)


def _output_slots(project: Any) -> Iterator[Union[_Slot, _ItemSlot, _FieldSlot]]:
    """Every field of ``project`` that names a file AERMOD writes, then
    every such field of the lines kept verbatim."""
    out = project.output
    for attr, keyword in (("summary_file", "SUMMFILE"), ("plot_file", "PLOTFILE"),
                          ("postfile", "POSTFILE")):
        yield _Slot(keyword, out, attr)
    for i in range(len(out.plot_file_groups)):
        yield _Slot("PLOTFILE", out.plot_file_groups, i)
    for keyword, entries in (
        ("MAXIFILE", out.maxi_files), ("RANKFILE", out.rank_files),
        ("SEASONHR", out.season_hour_files), ("EVALFILE", out.eval_files),
        ("TOXXFILE", out.toxx_files), ("MAXDAILY", out.max_daily_files),
        ("MXDYBYYR", out.max_daily_by_year_files),
        ("MAXDCONT", out.max_daily_contributions),
    ):
        for entry in entries:
            yield _Slot(keyword, entry, "filename")
    control = project.control
    yield _Slot("EVENTFIL", control, "eventfil")
    if control.save_file is not None:
        yield _Slot("SAVEFILE", control.save_file, "filename")
        yield _Slot("SAVEFILE", control.save_file, "alternate_filename")
    if control.multiyear is not None:
        yield _Slot("MULTYEAR", control.multiyear, "save_file")
    # CO DEBUGOPT (ControlPathway.debug_options): each field that is not
    # an option name is the file of the option before it.
    debug = control.debug_options
    for i, tok in enumerate(debug):
        if tok.upper() not in _DEBUG_OPTIONS:
            yield _ItemSlot("DEBUGOPT", debug, i)
    scim = project.meteorology.scim
    if scim is not None:
        yield _Slot("SCIMBYHR", scim, "surface_summary_file")
        yield _Slot("SCIMBYHR", scim, "profile_summary_file")
    yield from _unparsed_slots(project, _UNPARSED_OUTPUTS)


def _input_slots(project: Any) -> Iterator[Union[_Slot, _FieldSlot]]:
    """Every field of ``project`` that names a file AERMOD reads, the met
    files first, then every such field of the lines kept verbatim."""
    met = project.meteorology
    yield _Slot("SURFFILE", met, "surface_file")
    yield _Slot("PROFFILE", met, "profile_file")
    control = project.control
    if control.init_file is not None:
        yield _Slot("INITFILE", control.init_file, "filename")
    if control.multiyear is not None:
        yield _Slot("MULTYEAR", control.multiyear, "init_file")
    chem = control.chemistry
    if chem is not None:
        ozone = chem.ozone_data
        if ozone is not None:
            yield _Slot("OZONEFIL", ozone, "ozone_file")
            for sector in sorted(ozone.by_sector):
                yield _Slot("OZONEFIL", ozone.by_sector[sector], "hourly_file")
        nox = chem.nox_background
        if nox is not None:
            yield _Slot("NOX_FILE", nox, "hourly_file")
            for sector in sorted(nox.by_sector):
                yield _Slot("NOX_FILE", nox.by_sector[sector], "hourly_file")
        else:
            yield _Slot("NOX_FILE", chem, "nox_file")
    # SO HOUREMIS cards the model holds (SourcePathway.hourly_emissions)
    for card in getattr(project.sources, "hourly_emissions", None) or []:
        yield _Slot("HOUREMIS", card, "filename")
    yield from _unparsed_slots(project, _UNPARSED_INPUTS)


def _basename(name: str) -> str:
    # A deck written on Windows may name C:\out\pit.plt; split on both.
    return re.split(r"[\\/]", name)[-1]


def rewrite_output_names(project: Any, prefix: str = "") -> Dict[str, List[str]]:
    """Point every output file ``project`` names into AERMOD's working directory.

    Each name becomes ``prefix`` + its bare file name, so
    ``../plotfiles/pit.plt`` becomes ``pit.plt`` and AERMOD writes it
    beside the deck. ``project`` is changed in place. Returns the new
    names by keyword, such as ``{"PLOTFILE": ["pit.plt"]}``.

    The names in the lines :mod:`pyaermod.input_reader` keeps verbatim
    (:attr:`~pyaermod.input_generator.AERMODProject.unparsed_lines`) are
    renamed too: a PLOTFILE with a rank below FIRST or with a unit, a
    second POSTFILE, and the file fields of MAXIFILE, RANKFILE,
    TOXXFILE, SEASONHR, EVALFILE, SUMMFILE, MAXDAILY, MXDYBYYR,
    MAXDCONT, ERRORFIL, EVENTFIL, SAVEFILE, MULTYEAR and DEBUGOPT. The
    debug files of ``ControlPathway.debug_options`` are renamed under
    ``DEBUGOPT``; a debug option given without a file name writes
    AERMOD's default name (``MODEL.DBG``, ``AREA.DBG``, ...) in the
    working directory, which is the run's own directory already.

    Raises ``ValueError`` when two outputs would end up with the same
    name (compared ignoring case, since the disk may ignore it), or when
    a new name is longer than AERMOD's :data:`MAX_FILENAME_LENGTH`
    characters.

    Only files AERMOD writes are renamed. Files it reads (met data,
    ``INITFILE``, ``HOUREMIS``, background and ozone files) are left as
    they are here; :func:`run_design` links those into each run's
    directory itself.
    """
    names: Dict[str, List[str]] = {}
    seen: Dict[str, str] = {}
    for slot in _output_slots(project):
        old = slot.get()
        if not old:
            continue
        if not _basename(old):
            raise ValueError(f"{slot.keyword} file name {old!r} has no file name part")
        new = prefix + _basename(old)
        if len(new) > MAX_FILENAME_LENGTH:
            raise ValueError(
                f"{slot.keyword} file name {new!r} is longer than AERMOD's "
                f"{MAX_FILENAME_LENGTH} characters"
            )
        key = new.lower()  # AERMOD's files may land on a case-insensitive disk
        if key in seen:
            raise ValueError(
                f"{slot.keyword} {old!r} and {seen[key]} would both be written "
                f"as {new!r} in the run directory; give them different file names"
            )
        seen[key] = f"{slot.keyword} {old!r}"
        slot.set(new)
        names.setdefault(slot.keyword, []).append(new)
    return names


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

@dataclass
class EnsembleManifestEntry(RunManifestEntry):
    """One run of a design, as :class:`EnsembleManifest` stores it.

    Extends :class:`~pyaermod.runner_utils.RunManifestEntry`, whose
    ``input_file`` here is the deck's path relative to the design root,
    ``status`` is ``pending``, ``success`` or ``failed``, and
    ``runtime_seconds`` is the run's wall time.
    """

    run_id: str = ""
    run_dir: str = ""                      # relative to the design root
    factors: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION
    input_sha256: Optional[str] = None     # of run.inp as written
    binary: Optional[str] = None           # path of the AERMOD binary used
    binary_sha256: Optional[str] = None
    aermod_version: Optional[str] = None   # from the .out banner, e.g. "26135"
    met_files: Dict[str, str] = field(default_factory=dict)   # role -> source path
    met_sha256: Dict[str, str] = field(default_factory=dict)  # role -> SHA-256
    # The other files the deck reads (HOUREMIS, ...): role -> source path, SHA-256
    input_files: Dict[str, str] = field(default_factory=dict)
    input_files_sha256: Dict[str, str] = field(default_factory=dict)
    # keyword -> names; after a successful run, DEBUGOPT keeps the files written
    outputs: Dict[str, List[str]] = field(default_factory=dict)
    git_commit: Optional[str] = None       # pyaermod's commit, when in a checkout
    git_dirty: Optional[bool] = None
    pyaermod_version: Optional[str] = None
    return_code: Optional[int] = None
    warning_count: Optional[int] = None
    warnings: List[str] = field(default_factory=list)
    fatal_count: Optional[int] = None
    started: Optional[str] = None          # ISO 8601, local time
    finished: Optional[str] = None


@dataclass
class EnsembleManifest(RunManifest):
    """A :class:`~pyaermod.runner_utils.RunManifest` keyed by run ID."""

    entry_type: ClassVar[Type[RunManifestEntry]] = EnsembleManifestEntry

    def put(self, entry: EnsembleManifestEntry, save: bool = True) -> None:
        """Store ``entry`` under its run ID, replacing any earlier one."""
        self.entries[entry.run_id] = entry
        if save:
            self.save()

    def to_dataframe(self):
        """One row per run, indexed by run ID; factors that are not
        numbers, strings or booleans are written as canonical JSON."""
        import pandas as pd

        rows = []
        for rid, e in self.entries.items():
            row: Dict[str, Any] = {"run_id": rid}
            for name, value in e.factors.items():
                row[f"factor.{name}"] = (
                    value if value is None or isinstance(value, (bool, int, float, str))
                    else canonical_json(value)
                )
            for f in dataclasses.fields(e):
                if f.name in ("run_id", "factors"):
                    continue
                value = getattr(e, f.name)
                row[f.name] = (json.dumps(value, sort_keys=True)
                               if isinstance(value, (dict, list)) else value)
            rows.append(row)
        return pd.DataFrame(rows).set_index("run_id") if rows else pd.DataFrame()

    def write_csv(self, path: Union[str, Path]) -> Path:
        """Write :meth:`to_dataframe` as CSV and return the path."""
        p = Path(path)
        self.to_dataframe().to_csv(p)
        return p


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@dataclass
class DesignRun:
    """One row of a design after :func:`run_design`."""

    run_id: str
    factors: Dict[str, Any]
    run_dir: Path
    entry: EnsembleManifestEntry
    result: Optional[AERMODRunResult] = None  # None when it was already done
    skipped: bool = False                     # True when resumed from the manifest

    @property
    def success(self) -> bool:
        return self.entry.status == "success"

    @property
    def deck(self) -> Path:
        return self.run_dir / DECK_NAME


@dataclass
class DesignResult(Mapping):
    """The runs of a design, keyed by run ID, in the order of its rows."""

    runs: Dict[str, DesignRun]
    root: Path
    manifest: EnsembleManifest
    n_workers: int
    elapsed_seconds: float

    def __getitem__(self, key: str) -> DesignRun:
        return self.runs[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.runs)

    def __len__(self) -> int:
        return len(self.runs)

    @property
    def n_skipped(self) -> int:
        """Runs already done, taken from the manifest without running AERMOD."""
        return sum(r.skipped for r in self.runs.values())

    @property
    def n_run(self) -> int:
        """Runs AERMOD made in this call."""
        return len(self.runs) - self.n_skipped

    @property
    def n_failed(self) -> int:
        return sum(not r.success for r in self.runs.values())

    @property
    def all_succeeded(self) -> bool:
        return self.n_failed == 0

    @property
    def run_seconds(self) -> float:
        """Total wall time of the runs made in this call, as each run measured it."""
        return sum(
            r.entry.runtime_seconds or 0.0 for r in self.runs.values() if not r.skipped
        )

    @property
    def concurrency(self) -> float:
        """:attr:`run_seconds` over :attr:`elapsed_seconds`: how many runs
        were in progress on average.

        It is not the speed-up over running one at a time: runs that share
        a machine slow each other down, so each run's own time is longer
        than it would be alone. Time the same design with ``n_workers=1``
        for the speed-up.
        """
        return self.run_seconds / self.elapsed_seconds if self.elapsed_seconds > 0 else 0.0

    def collect_plotfiles(self, out_stem: Optional[Union[str, Path]] = "plotfiles"):
        """:func:`collect_plotfiles` for these runs only."""
        return collect_plotfiles(self.root, run_ids=list(self.runs), out_stem=out_stem)

    def to_dataframe(self):
        """One row per run, indexed by run ID: the factors, then the status."""
        import pandas as pd

        rows = []
        for rid, r in self.runs.items():
            row = {"run_id": rid, **r.factors}
            row.update(
                status=r.entry.status, skipped=r.skipped,
                runtime_seconds=r.entry.runtime_seconds,
                warning_count=r.entry.warning_count,
                error_message=r.entry.error_message,
                run_dir=str(r.run_dir),
            )
            rows.append(row)
        return pd.DataFrame(rows).set_index("run_id") if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# run_design
# ---------------------------------------------------------------------------

def _rows_as_dicts(rows: Any) -> List[Dict[str, Any]]:
    to_dict = getattr(rows, "to_dict", None)
    if callable(to_dict) and hasattr(rows, "columns"):  # a pandas DataFrame
        rows = to_dict(orient="records")
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(f"design row {i} is a {type(row).__name__}, not a mapping of factors")
        bad = [k for k in row if not isinstance(k, str)]
        if bad:
            raise TypeError(f"design row {i} has factor names that are not strings: {bad!r}")
        clash = sorted(_RESERVED_COLUMNS & set(row))
        if clash:
            raise ValueError(
                f"design row {i} uses the reserved factor name(s) {clash}; "
                f"rename them (reserved: {sorted(_RESERVED_COLUMNS)})"
            )
        out.append(dict(row))
    return out


def _git_commit() -> Tuple[Optional[str], Optional[bool]]:
    """pyaermod's git commit and whether its tracked files differ from it.

    ``(None, None)`` unless pyaermod runs from a git checkout of itself:
    an installed copy inside some other repository (a virtual
    environment in a project's tree) must not report that project's
    commit, so the package's ``__init__.py`` must be tracked there.
    """
    here = Path(__file__).resolve().parent
    try:
        tracked = subprocess.run(
            ["git", "-C", str(here), "ls-files", "--error-unmatch", "__init__.py"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if tracked.returncode != 0:
            return None, None
        head = subprocess.run(
            ["git", "-C", str(here), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if head.returncode != 0:
            return None, None
        status = subprocess.run(
            ["git", "-C", str(here), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
    return head.stdout.strip(), dirty


def _aermod_version(out_path: Path) -> Optional[str]:
    """The version in the ``*** AERMOD - VERSION nnnnn ***`` banner of an .out."""
    try:
        with open(out_path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(256_000)
    except OSError:
        return None
    m = _VERSION_BANNER.search(head)
    return m.group(1) if m else None


def _link_or_copy(src: Path, dst: Path) -> None:
    """Put ``src`` at ``dst``: a symbolic link, else a hard link, else a copy."""
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    try:
        dst.symlink_to(src)
    except OSError:
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


@dataclass
class _Planned:
    index: int
    run_id: str
    factors: Dict[str, Any]
    run_dir: Path
    deck_text: str
    entry: EnsembleManifestEntry
    links: List[Tuple[Path, str]]  # (source, link name) of each input file
    done: bool = False


def _is_done(entry: Optional[RunManifestEntry], plan: _Planned) -> bool:
    """Whether the manifest's run of ``plan`` finished and its files are intact.

    The entry must say success for this very deck (the SHA-256 of the
    deck text) with the same binary, met and input files (their
    SHA-256), the deck on disk must be that deck, the ``.out`` must
    carry AERMOD's success banner and a copy of this deck (the rule of
    ``resume_batch``), and every PLOTFILE and POSTFILE the run named
    must still exist, as must every debug file it wrote.
    """
    if not isinstance(entry, EnsembleManifestEntry) or entry.status != "success":
        return False
    want = plan.entry
    if (entry.schema_version, entry.binary_sha256, entry.met_sha256, entry.input_files_sha256) != (
            want.schema_version, want.binary_sha256, want.met_sha256, want.input_files_sha256):
        return False
    sha = hashlib.sha256(plan.deck_text.encode("utf-8")).hexdigest()
    deck = plan.run_dir / DECK_NAME
    if entry.input_sha256 != sha or not deck.exists() or file_sha256(deck) != sha:
        return False
    if not _output_is_valid(plan.run_dir / f"{Path(DECK_NAME).stem}.out", deck):
        return False
    return all((plan.run_dir / name).exists()
               for keyword in _REQUIRED_OUTPUTS
               for name in entry.outputs.get(keyword, []))


def _finish_entry(entry: EnsembleManifestEntry, result: AERMODRunResult) -> None:
    entry.status = "success" if result.success else "failed"
    entry.runtime_seconds = result.runtime_seconds
    entry.error_message = result.error_message
    entry.return_code = result.return_code
    entry.warning_count = result.warning_count
    entry.fatal_count = result.fatal_count
    entry.warnings = [str(m) for m in result.warning_messages]
    entry.started = result.start_time.isoformat(timespec="seconds") if result.start_time else None
    entry.finished = result.end_time.isoformat(timespec="seconds") if result.end_time else None
    if result.output_file:
        entry.aermod_version = _aermod_version(Path(result.output_file))


def _drop_unwritten(entry: EnsembleManifestEntry, run_dir: Path) -> None:
    """After a successful run, drop from ``entry.outputs`` the debug files
    the deck named but AERMOD did not open, so ``outputs`` lists the
    files the run wrote and resuming it does not wait for them."""
    for keyword in _MAYBE_UNWRITTEN:
        names = entry.outputs.get(keyword)
        if names is None:
            continue
        kept = [n for n in names if (run_dir / n).exists()]
        if kept:
            entry.outputs[keyword] = kept
        else:
            del entry.outputs[keyword]


def run_design(
    rows: Iterable[Mapping[str, Any]],
    build_fn: Callable[[Dict[str, Any]], Any],
    root: Union[str, Path],
    n_workers: int = 4,
    *,
    executable: Optional[Union[str, Path]] = None,
    timeout: int = 3600,
    resume: bool = True,
    validate: bool = True,
    progress: Optional[ProgressReporter] = None,
) -> DesignResult:
    """Run one AERMOD run per design row, each in its own directory.

    For each row, ``build_fn(factors)`` returns an
    :class:`~pyaermod.input_generator.AERMODProject`. :func:`run_design`
    works on a deep copy of it:

    1. The files it has AERMOD read are hashed: the met files
       (``SURFFILE``, ``PROFFILE``), ``INITFILE``, the ``MULTYEAR``
       initial file, ``OZONEFIL`` and ``NOX_FILE`` files, the
       ``HOUREMIS`` files of ``SourcePathway.hourly_emissions``, and, in
       the lines kept verbatim, ``HOUREMIS``, hourly ``BACKGRND`` files
       and ``INCLUDED`` files. A relative path is taken relative to the
       current directory. The run ID is computed from the factors and
       the SHA-256 of the binary and of these files (:func:`run_id`), so
       editing an emission file makes a new run.
    2. The run's directory is ``root/runs/<run ID>``. The input files are
       linked into it and the deck names them by their bare names, and
       every output file name is rewritten to a bare name in the same
       directory (:func:`rewrite_output_names`), so no run can overwrite
       another's files. An ``INCLUDED`` file is linked as it is: the
       file names inside it are not rewritten.
    3. The deck is written there as ``run.inp`` and run with
       :class:`~pyaermod.runner.AERMODRunner`, ``n_workers`` at a time.

    The manifest ``root/manifest.json`` gets an entry per run before any
    run starts, and each entry is updated (and the file saved) as its run
    finishes, so it always shows which runs have finished. ``manifest.csv``
    beside it is written at the end. ``root/design.json`` lists this
    call's run IDs, in row order, before any run starts; the manifest
    keeps the runs of earlier calls too.

    With ``resume=True`` (the default), a run is skipped when its
    manifest entry says it succeeded for the same deck text and input
    files, the deck on disk is that deck, its ``.out`` has AERMOD's
    success banner and a copy of that deck, and its PLOTFILEs,
    POSTFILEs and the debug files it wrote are all present. Any other
    run is made again: a run that failed or was cut off, one whose
    ``build_fn`` now writes a different deck, and one whose files were
    removed. Running the same design again after an interrupt therefore
    makes only the runs that had not finished.

    Workers are processes. On macOS and Windows a script must call this
    function from under ``if __name__ == "__main__":`` (see
    :meth:`~pyaermod.runner.AERMODRunner.run_batch`). ``n_workers=1``
    runs every deck in this process, one after another.

    Args:
        rows: the design: mappings of factor name to value, or a pandas
            DataFrame (one run per row). Factor values must be writable by
            :func:`canonical_json`; two rows with the same factors are an
            error.
        build_fn: called with a copy of each row's factors, returns the
            project for that run.
        root: directory for the design (created if needed).
        n_workers: number of runs at a time.
        executable: the AERMOD binary; by default, ``aermod`` on PATH.
        timeout: seconds allowed for each run.
        resume: skip runs the manifest shows as done (see above). With
            False every run is made again.
        validate: validate each project before writing its deck.
        progress: a :class:`~pyaermod.runner_utils.ProgressReporter`
            told about each finished run.

    Returns:
        A :class:`DesignResult`: the runs keyed by run ID, in row order.

    Raises:
        FileNotFoundError: a met file or other input file does not exist.
        ValueError: duplicate rows, an input file name longer than
            AERMOD's 200 characters, or input and output file names that
            collide in the run directory.
    """
    started = time.perf_counter()
    design = _rows_as_dicts(rows)
    root_path = Path(root).resolve()
    runs_dir = root_path / RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)

    runner = AERMODRunner(executable_path=executable, log_level="WARNING")
    binary = Path(runner.executable).resolve()
    binary_sha = file_sha256(binary)
    commit, dirty = _git_commit()
    from . import __version__ as pyaermod_version

    manifest = EnsembleManifest.load(root_path / MANIFEST_NAME)
    file_cache: Dict[Path, str] = {}
    plans: List[_Planned] = []
    by_id: Dict[str, int] = {}

    for index, factors in enumerate(design):
        project = copy.deepcopy(build_fn(dict(factors)))
        met_sha: Dict[str, str] = {}
        met_src: Dict[str, Path] = {}
        input_sha: Dict[str, str] = {}
        input_src: Dict[str, Path] = {}
        role_of: Dict[Path, str] = {}
        per_keyword: Dict[str, int] = {}
        named: List[Tuple[Any, Path]] = []
        for slot in _input_slots(project):
            given = slot.get()
            what = _describe_input(slot.keyword)
            if not given and slot.keyword not in _MET_ROLES:
                continue
            src = Path(given or "").expanduser()
            src = (src if src.is_absolute() else Path.cwd() / src).resolve()
            if not src.is_file():
                raise FileNotFoundError(f"design row {index}: {what} not found: {src}")
            if src not in file_cache:
                file_cache[src] = file_sha256(src)
            named.append((slot, src))
            if slot.keyword in _MET_ROLES:
                role = _MET_ROLES[slot.keyword]
                met_sha[role], met_src[role] = file_cache[src], src
            elif src not in role_of:
                n = per_keyword[slot.keyword] = per_keyword.get(slot.keyword, 0) + 1
                role = slot.keyword if n == 1 else f"{slot.keyword}.{n}"
                role_of[src] = role
                input_sha[role], input_src[role] = file_cache[src], src
        rid = run_id(factors, binary_sha, met_sha, input_sha)
        if rid in by_id:
            raise ValueError(
                f"design rows {by_id[rid]} and {index} have the same factors "
                f"({canonical_json(factors)}), so they would be the same run"
            )
        by_id[rid] = index

        outputs = rewrite_output_names(project)
        taken = {n.lower() for names in outputs.values() for n in names}
        clash = sorted(taken & _RESERVED_FILES)
        if clash:
            raise ValueError(
                f"design row {index}: output file name(s) {clash} are used in "
                "the run directory by the runner; choose other names"
            )
        taken |= _RESERVED_FILES
        link_name: Dict[Path, str] = {}
        for slot, src in named:
            name = link_name.get(src)
            if name is None:
                name = src.name
                what = _describe_input(slot.keyword)
                if len(name) > MAX_FILENAME_LENGTH:
                    raise ValueError(
                        f"design row {index}: the {what} name {name!r} is "
                        f"longer than AERMOD's {MAX_FILENAME_LENGTH} characters"
                    )
                if name.lower() in taken:
                    raise ValueError(
                        f"design row {index}: the {what} {name!r} has the name of "
                        "another file in the run directory; rename one of them"
                    )
                taken.add(name.lower())
                link_name[src] = name
            slot.set(name)

        deck_text = project.to_aermod_input(validate=validate)
        run_dir = runs_dir / rid
        entry = EnsembleManifestEntry(
            input_file=(Path(RUNS_DIR) / rid / DECK_NAME).as_posix(),
            status="pending",
            run_id=rid,
            run_dir=(Path(RUNS_DIR) / rid).as_posix(),
            factors=json.loads(canonical_json(factors)),
            input_sha256=hashlib.sha256(deck_text.encode("utf-8")).hexdigest(),
            binary=str(binary),
            binary_sha256=binary_sha,
            met_files={role: str(p) for role, p in met_src.items()},
            met_sha256=met_sha,
            input_files={role: str(p) for role, p in input_src.items()},
            input_files_sha256=input_sha,
            outputs=outputs,
            git_commit=commit,
            git_dirty=dirty,
            pyaermod_version=pyaermod_version,
        )
        plan = _Planned(index, rid, dict(factors), run_dir, deck_text, entry,
                        list(link_name.items()))
        plan.done = resume and _is_done(manifest.entries.get(rid), plan)
        plans.append(plan)

    todo = [p for p in plans if not p.done]
    for plan in todo:
        plan.run_dir.mkdir(parents=True, exist_ok=True)
        # An earlier attempt's outputs must not outlive a run that fails
        # before writing its own.
        for names in plan.entry.outputs.values():
            for name in names:
                with contextlib.suppress(FileNotFoundError):
                    (plan.run_dir / name).unlink()
        for src, name in plan.links:
            _link_or_copy(src, plan.run_dir / name)
        payload = run_id_payload(plan.factors, binary_sha, plan.entry.met_sha256,
                                 plan.entry.input_files_sha256)
        _write_text_atomic(plan.run_dir / FACTORS_NAME,
                           json.dumps(json.loads(canonical_json(payload)), indent=2,
                                      sort_keys=True) + "\n")
        _write_text_atomic(plan.run_dir / DECK_NAME, plan.deck_text)
        manifest.put(plan.entry, save=False)
    manifest.save()
    _write_text_atomic(root_path / DESIGN_NAME, json.dumps(
        {"schema_version": SCHEMA_VERSION, "run_ids": [p.run_id for p in plans]},
        indent=2) + "\n")

    logger.info("Design %s: %d runs, %d already done, %d to run on %d worker(s)",
                root_path, len(plans), len(plans) - len(todo), len(todo), n_workers)
    reporter = progress
    if reporter is not None:
        reporter.start(len(todo), description="AERMOD runs")

    results: Dict[str, AERMODRunResult] = {}

    def _record(plan: _Planned, result: AERMODRunResult) -> None:
        _finish_entry(plan.entry, result)
        if plan.entry.status == "success":
            _drop_unwritten(plan.entry, plan.run_dir)
        manifest.put(plan.entry)
        results[plan.run_id] = result
        if reporter is not None:
            reporter.update(1, message=f"{plan.run_id[:12]} {plan.entry.status}")

    if todo and n_workers <= 1:
        for plan in todo:
            _record(plan, runner.run(plan.run_dir / DECK_NAME, timeout=timeout))
    elif todo:
        executor = ProcessPoolExecutor(max_workers=min(n_workers, len(todo)))
        try:
            futures = {
                executor.submit(_batch_worker, str(binary), str(p.run_dir / DECK_NAME), timeout): p
                for p in todo
            }
            for future in as_completed(futures):
                plan = futures[future]
                try:
                    result = future.result()
                except Exception as exc:  # a worker died (spawn guard, OOM kill)
                    result = AERMODRunResult(
                        success=False, input_file=str(plan.run_dir / DECK_NAME),
                        error_message=f"The worker running this deck failed: {exc}",
                    )
                _record(plan, result)
        except BaseException:
            # Interrupted (Ctrl-C) or failed: do not wait for queued runs.
            # The manifest already holds every run that finished.
            executor.shutdown(wait=False, cancel_futures=True)
            raise
        executor.shutdown(wait=True)

    if reporter is not None:
        reporter.finish()
    with contextlib.suppress(OSError):
        manifest.write_csv(root_path / "manifest.csv")

    runs: Dict[str, DesignRun] = {}
    for plan in plans:
        entry = plan.entry
        if plan.done:
            stored = manifest.entries[plan.run_id]
            assert isinstance(stored, EnsembleManifestEntry)
            entry = stored
        runs[plan.run_id] = DesignRun(
            run_id=plan.run_id, factors=plan.factors, run_dir=plan.run_dir,
            entry=entry, result=results.get(plan.run_id), skipped=plan.done,
        )
    return DesignResult(
        runs=runs, root=root_path, manifest=manifest,
        n_workers=n_workers, elapsed_seconds=time.perf_counter() - started,
    )


# ---------------------------------------------------------------------------
# collect_plotfiles
# ---------------------------------------------------------------------------

def _column_name(label: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", label.lower()).strip("_")


def collect_plotfiles(
    root: Union[str, Path],
    run_ids: Optional[Iterable[str]] = None,
    out_stem: Optional[Union[str, Path]] = "plotfiles",
):
    """Read the PLOTFILEs of a design's successful runs into one tidy table.

    One row per receptor of each PLOTFILE of each run whose manifest
    entry says ``success``, among the runs of ``run_ids``. By default
    those are the runs of the latest :func:`run_design` call on
    ``root`` (``root/design.json``), not every run the manifest holds:
    it keeps the runs of rows since dropped and of an earlier binary or
    met file too. Pass ``run_ids=manifest.entries`` for all of them. The
    columns are ``run_id``, ``plotfile`` (its file name), ``receptor``
    (the row's position in its file, from 0), then AERMOD's own columns
    in lower case with underscores: ``x``, ``y``, ``average_conc``,
    ``total_depo``, ``dry_depo``, ``wet_depo``, ``zelev``, ``zhill``,
    ``zflag``, ``ave``, ``grp``, ``num_hrs``, ``net_id``, as the file has
    them. A column one file lacks is empty (NaN) in its rows. Factors
    are not repeated here; join on ``run_id`` with the manifest
    (:meth:`EnsembleManifest.to_dataframe`) or :class:`DesignResult`.

    The files are read with :func:`pyaermod.aermod_outputs.read_plotfile`.

    Unless ``out_stem`` is None, the table is also written as
    ``<out_stem>.csv`` and ``<out_stem>.npz`` (relative to ``root``
    unless absolute). The ``.npz`` holds one array per column, strings
    as NumPy unicode arrays, so ``numpy.load(path)`` reads it without
    ``allow_pickle``.

    Raises:
        FileNotFoundError: a successful run's PLOTFILE is missing.
    """
    import numpy as np
    import pandas as pd

    from .aermod_outputs import read_plotfile

    root_path = Path(root).resolve()
    manifest = EnsembleManifest.load(root_path / MANIFEST_NAME)
    if run_ids is None and (root_path / DESIGN_NAME).exists():
        run_ids = json.loads((root_path / DESIGN_NAME).read_text(encoding="utf-8"))["run_ids"]
    wanted = None if run_ids is None else set(run_ids)
    frames = []
    for rid, entry in manifest.entries.items():
        if wanted is not None and rid not in wanted:
            continue
        if not isinstance(entry, EnsembleManifestEntry) or entry.status != "success":
            continue
        run_dir = root_path / entry.run_dir
        for name in entry.outputs.get("PLOTFILE", []):
            path = run_dir / name
            if not path.exists():
                raise FileNotFoundError(f"run {rid}: PLOTFILE {name} is missing ({path})")
            res = read_plotfile(path)
            df = pd.DataFrame(res.records)
            df.columns = [_column_name(c) for c in df.columns]
            df.insert(0, "receptor", np.arange(len(df), dtype=np.int64))
            df.insert(0, "plotfile", name)
            df.insert(0, "run_id", rid)
            frames.append(df)
    if frames:
        table = pd.concat(frames, ignore_index=True, sort=False)
    else:
        table = pd.DataFrame(columns=["run_id", "plotfile", "receptor"])

    if out_stem is not None:
        stem = Path(out_stem)
        if not stem.is_absolute():
            stem = root_path / stem
        stem.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(stem.with_name(stem.name + ".csv"), index=False)
        arrays = {}
        for col in table.columns:
            values = table[col].to_numpy()
            if values.dtype.kind not in "biuf":
                # Text (and any mixed column) as a NumPy unicode array, so
                # that numpy.load needs no pickle; a missing value is "".
                values = np.array(["" if pd.isna(v) else str(v) for v in values], dtype=str)
            arrays[col] = values
        np.savez_compressed(stem.with_name(stem.name + ".npz"), **arrays)
    return table


__all__ = [
    "DECK_NAME",
    "DESIGN_NAME",
    "MAX_FILENAME_LENGTH",
    "SCHEMA_VERSION",
    "DesignResult",
    "DesignRun",
    "EnsembleManifest",
    "EnsembleManifestEntry",
    "canonical_json",
    "collect_plotfiles",
    "file_sha256",
    "rewrite_output_names",
    "run_design",
    "run_id",
    "run_id_payload",
]

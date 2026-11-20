"""
Reading an AERMOD ``.inp`` deck into a project, with no UI.

:func:`read_deck` is what :meth:`Session.import_inp
<pyaermod.gui_v2.session.Session.import_inp>` reads a deck with: the
project, checked, and a :class:`DeckImport` saying what came in and
which of the deck's files the user still has to supply.
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, Union

from ..input_generator import AERMODProject
from .project_io import check_project

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..unparsed import UnparsedLine

logger = logging.getLogger(__name__)


class DeckImportError(ValueError):
    """:meth:`Session.import_inp` could not import the deck.

    The message starts with the deck's name and says why, in words meant
    for the user; nothing in the session has changed.
    """


#: The met file fields an imported deck names, and how the GUI calls them.
MET_FILE_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("surface_file", "surface"),
    ("profile_file", "profile"),
)

#: The name an uploaded deck is shown under when it came without one.
_DEFAULT_DECK_NAME = "deck.inp"

#: The file an upload is written to in its temporary folder: the name the
#: user sees may be longer than a file name can be.
_UPLOAD_FILE_NAME = "upload.inp"

#: How long a deck's name may be in the header and in messages.
_MAX_DECK_NAME = 120

#: The deck keyword that names each met file field.
_MET_KEYWORDS = {"ME SURFFILE": "surface_file", "ME PROFFILE": "profile_file"}


@dataclass(frozen=True)
class DeckImport:
    """What :meth:`Session.import_inp` brought in, for the notice the GUI shows.

    ``path`` is the deck's file on this computer, or None for an upload.
    ``unparsed`` holds the lines the reader kept as written
    (:attr:`AERMODProject.unparsed_lines`). ``met_found`` names the met
    file fields whose relative path was found beside the deck and is now
    a full path; ``met_needed`` lists ``(field, path as written)`` for
    each met file the user still has to point at. The deck's other input
    files (ozone and NOx files, ``INCLUDED``, ``HOUREMIS`` ...; see
    :func:`~pyaermod.input_reader.input_files`) are listed as
    ``(keyword, path as written)``: ``inputs_found`` for those found
    beside the deck, now full paths, and ``inputs_missing`` for those
    that are not a file on this computer as the project names them.
    """

    name: str
    path: Optional[Path]
    unparsed: Tuple[UnparsedLine, ...] = ()
    met_found: Tuple[str, ...] = ()
    met_needed: Tuple[Tuple[str, str], ...] = ()
    inputs_found: Tuple[Tuple[str, str], ...] = ()
    inputs_missing: Tuple[Tuple[str, str], ...] = ()


def read_deck(source: Union[str, bytes, Path],
              name: str = "") -> Tuple[AERMODProject, DeckImport]:
    """The project an AERMOD ``.inp`` deck describes, and what came in.

    A :class:`~pathlib.Path` is a deck on this computer that the user
    chose (a native dialog, a path they typed, the recent-files list):
    it is read as it stands, and each file it reads (met, ozone,
    ``INCLUDED`` ...) named by a relative path that exists beside it
    becomes a full path (:func:`~pyaermod.input_reader.anchor_input_files`),
    so a run in any working directory finds it. Text or bytes are an
    upload, whose folder the server never sees: the deck is read with
    ``read_aermod_input(..., sandbox=True)`` from a private temporary
    folder, so no path in it, kept-as-written lines included, may
    lead outside its own folder, and every file it reads is one the
    user still has to supply. ``name`` is the upload's bare file name
    (``""`` when it came without one).

    Raises :class:`DeckImportError` when the deck cannot be imported.
    """
    from ..input_reader import anchor_input_files

    if isinstance(source, Path):
        deck_name = _shorten_deck_name(source.name or _DEFAULT_DECK_NAME)
        project = _read_deck(source, deck_name, sandbox=False)
        anchored = [ref for ref, _full in anchor_input_files(project, source.parent)]
        path: Optional[Path] = source
    else:
        deck_name = _shorten_deck_name(name or _DEFAULT_DECK_NAME)
        data = source.encode("utf-8") if isinstance(source, str) else source
        with tempfile.TemporaryDirectory(prefix="pyaermod_import_") as tmp:
            deck = Path(tmp) / _UPLOAD_FILE_NAME
            try:
                deck.write_bytes(data)
            except OSError as exc:
                raise DeckImportError(
                    f"{deck_name}: could not be stored for reading: "
                    f"{exc.strerror or exc}") from exc
            project = _read_deck(deck, deck_name, sandbox=True)
        anchored, path = [], None
    try:
        # The project as its file would reopen it, like every project the
        # session holds: a value the pages or the deck writer could not
        # use is refused here, by field.
        project = check_project(project, origin=deck_name)
    except (ValueError, TypeError) as exc:
        raise DeckImportError(str(exc)) from exc
    return project, DeckImport(
        name=deck_name, path=path, unparsed=tuple(project.unparsed_lines),
        met_found=tuple(_MET_KEYWORDS[ref.keyword] for ref in anchored
                        if ref.keyword in _MET_KEYWORDS),
        met_needed=_met_needed(project),
        inputs_found=tuple((ref.keyword, ref.path) for ref in anchored
                           if ref.keyword not in _MET_KEYWORDS),
        inputs_missing=_inputs_missing(project),
    )


def _read_deck(deck: Path, name: str, *, sandbox: bool) -> AERMODProject:
    from ..input_reader import PathTraversalError, read_aermod_input

    try:
        return read_aermod_input(deck, sandbox=sandbox)
    except PathTraversalError as exc:
        outside = "; ".join(f"{v.path} ({v.field})" for v in exc.violations) or str(exc)
        raise DeckImportError(
            f"{name}: an uploaded deck may only name files in its own folder, and "
            f"this one names {outside}. Import it from its path on this computer "
            f"instead, or change those paths in the deck.") from exc
    except UnicodeDecodeError as exc:
        raise DeckImportError(f"{name}: not a UTF-8 text file") from exc
    except OSError as exc:
        raise DeckImportError(f"{name}: {exc.strerror or exc}") from exc
    except ValueError as exc:
        raise DeckImportError(f"{name}: not an AERMOD deck PyAERMOD can read: {exc}") from exc
    except Exception as exc:
        # The reader raised something it does not document: a bug in
        # the reader, so the traceback goes to the log.
        logger.exception("Reading deck %s raised", name)
        raise DeckImportError(
            f"{name}: could not be read ({type(exc).__name__}: {exc})") from exc


def _shorten_deck_name(name: str) -> str:
    """``name``, cut to fit the header, keeping its suffix."""
    if len(name) <= _MAX_DECK_NAME:
        return name
    suffix = Path(name).suffix if len(Path(name).suffix) <= 10 else ""
    return name[:_MAX_DECK_NAME - len(suffix) - 3] + "..." + suffix


def _is_local_file(raw: str) -> bool:
    try:
        return Path(raw).is_absolute() and Path(raw).is_file()
    except (OSError, ValueError):
        return False


def _met_needed(project: AERMODProject) -> Tuple[Tuple[str, str], ...]:
    """``(field, path)`` for each met file that is not a file on this computer."""
    met = project.meteorology
    needed = []
    for field_name, _label in MET_FILE_FIELDS:
        raw = getattr(met, field_name, None) or ""
        if not (raw and _is_local_file(raw)):
            needed.append((field_name, raw))
    return tuple(needed)


def _inputs_missing(project: AERMODProject) -> Tuple[Tuple[str, str], ...]:
    """``(keyword, path)`` for each other input file not on this computer."""
    from ..input_reader import input_files

    return tuple((ref.keyword, ref.path) for ref in input_files(project)
                 if ref.keyword not in _MET_KEYWORDS and not _is_local_file(ref.path))


__all__ = ["MET_FILE_FIELDS", "DeckImport", "DeckImportError", "read_deck"]

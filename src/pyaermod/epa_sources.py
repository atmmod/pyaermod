"""
Registry of EPA SCRAM download locations for the model source archives.

Every URL here was **discovered** by listing the SCRAM directory it
lives in, then verified to return an ``application/zip`` response --
not guessed from a naming pattern. Guessing does not work: AERSCREEN is
under ``models/screening/``, not ``models/related/`` where the other
auxiliary programs live; the AERSURFACE test cases are
``aersurface_testcase.zip`` (singular) while AERSCREEN's are
``aerscreen_test_cases.zip`` (plural); and BPIP-PRIME ships as
``bpipprime.zip``, not ``bpipprm_source.zip``.

``tests/test_epa_sources.py`` re-lists each directory and fails if a
registered file is no longer there, so a rename on EPA's side surfaces
as a test failure rather than as a 404 in CI months later.

Use :func:`listing_url` and re-run the discovery when adding an entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

SCRAM_ROOT = "https://gaftp.epa.gov/Air/aqmg/SCRAM/models"


@dataclass(frozen=True)
class EPASource:
    """One downloadable archive on EPA SCRAM.

    Attributes
    ----------
    program
        Model or utility the archive belongs to (``"aermod"``, ``"bpip"``).
    kind
        ``"source"``, ``"test_cases"`` or ``"executable"``.
    directory
        SCRAM path below :data:`SCRAM_ROOT`, e.g. ``"preferred/aermod"``.
    filename
        Archive filename exactly as EPA publishes it.
    note
        Anything a caller needs to know before using it.
    """

    program: str
    kind: str
    directory: str
    filename: str
    note: str = ""

    @property
    def url(self) -> str:
        return f"{SCRAM_ROOT}/{self.directory}/{self.filename}"

    @property
    def listing_url(self) -> str:
        """Directory listing the archive was discovered in."""
        return f"{SCRAM_ROOT}/{self.directory}/"

    @property
    def key(self) -> str:
        return f"{self.program}_{self.kind}"


_SOURCES = (
    EPASource("aermod", "source", "preferred/aermod", "aermod_source.zip"),
    EPASource("aermod", "test_cases", "preferred/aermod",
              "aermod_test_cases.zip",
              "489 MB; three aermet*_aermod* reference sets"),
    EPASource("aermet", "source", "met/aermet", "aermet_source.zip"),
    EPASource("aermet", "test_cases", "met/aermet", "aermet_test_cases.zip",
              "459 MB; extracts flat, not into a versioned subdirectory"),
    EPASource("aermap", "source", "related/aermap", "aermap_source.zip"),
    EPASource("aersurface", "source", "related/aersurface",
              "aersurface_source.zip"),
    EPASource("aersurface", "test_cases", "related/aersurface",
              "aersurface_testcase.zip",
              "singular 'testcase', unlike every other program"),
    EPASource("bpip", "source", "related/bpip", "bpip.zip",
              "the original BPIP, without the PRIME algorithm"),
    EPASource("bpipprime", "source", "related/bpip", "bpipprime.zip",
              "BPIP-PRIME: the one AERMOD's downwash inputs come from. "
              "Ships Fortran source plus eight worked examples with "
              "their reference output"),
    EPASource("aerscreen", "source", "screening/aerscreen",
              "aerscreen_code.zip",
              "under screening/, not related/"),
    EPASource("aerscreen", "test_cases", "screening/aerscreen",
              "aerscreen_test_cases.zip", "46 MB"),
    EPASource("makemet", "source", "screening/aerscreen", "makemet_code.zip",
              "AERSCREEN's meteorology pre-processor"),
)

#: Every registered archive, keyed by ``"<program>_<kind>"``.
EPA_SOURCES: Dict[str, EPASource] = {s.key: s for s in _SOURCES}


def get_source(program: str, kind: str = "source") -> EPASource:
    """Look up one registered archive.

    Raises
    ------
    KeyError
        If the pair is not registered; the message lists what is.
    """
    key = f"{program.lower()}_{kind.lower()}"
    try:
        return EPA_SOURCES[key]
    except KeyError:
        raise KeyError(
            f"No EPA source registered for {program!r}/{kind!r}; "
            f"available: {sorted(EPA_SOURCES)}"
        ) from None


def source_url(program: str, kind: str = "source") -> str:
    """Download URL for one registered archive."""
    return get_source(program, kind).url


def listing_url(program: str, kind: str = "source") -> str:
    """SCRAM directory listing an archive was discovered in."""
    return get_source(program, kind).listing_url


def programs() -> Dict[str, Optional[str]]:
    """Map each registered program to its source-archive URL, if any."""
    out: Dict[str, Optional[str]] = {}
    for s in _SOURCES:
        out.setdefault(s.program, None)
        if s.kind == "source":
            out[s.program] = s.url
    return out


__all__ = [
    "EPA_SOURCES",
    "SCRAM_ROOT",
    "EPASource",
    "get_source",
    "listing_url",
    "programs",
    "source_url",
]

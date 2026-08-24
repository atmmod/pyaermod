"""
Locate EPA's AERMOD test-case reference sets on disk.

EPA publishes the AERMOD test cases as a zip that unpacks into one or
more *reference sets*. Each set is a self-contained tree::

    <set>/inputs/*.inp        the test decks (53 in the 2026 bundle)
    <set>/meteorology/        the .SFC/.PFL files the decks reference
    <set>/postfiles/*.PST     EPA's reference POSTFILEs
    <set>/plotfiles/*.PLT
    <set>/Outputs/*.out, *.SUM

A set's directory name carries the AERMET and AERMOD versions that
produced its references, in one of two spellings: the pre-2026 bundle
shipped a single ``aermet_24142_aermod_24142`` set, while the July 2026
bundle ships ``aermet24142_aermod24142``, ``aermet24142_aermod26135`` and
``aermet26135_aermod26135`` side by side. Everything in pyaermod that
consumes the fixtures — the regulatory parity harness under
``tests/regulatory/``, the parser regression tests, and
``scripts/run_epa_parity.py`` — goes through :func:`find_epa_testcase_set`
so the naming drift and the choice between sets are handled in exactly
one place.

Selection rules
---------------
1. If :data:`ENV_VAR` (``PYAERMOD_EPA_TESTCASES``) is set, it names the
   set directory to use; nothing else is consulted.
2. Otherwise every ``aermet*_aermod*`` directory under the root
   (``<repo>/test_cases`` by convention) is a candidate. When
   ``aermod_version`` is given — normally the version of the AERMOD
   binary under test, see :func:`aermod_binary_version` — a set produced
   by that AERMOD version is preferred, so a model-version mismatch can
   never masquerade as a pyaermod regression.
3. Without a version hint (no binary on PATH), a set produced by a
   *validated* AERMOD release (:data:`pyaermod.versions.VALIDATED_AERMOD_VERSIONS`,
   newest first — so 26135 over 24142) is preferred.
4. Remaining ties resolve to the newest set: highest AERMOD version,
   then highest AERMET version.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Union

from .versions import VALIDATED_AERMOD_VERSIONS

#: Environment variable that pins the test-case set directory explicitly.
ENV_VAR = "PYAERMOD_EPA_TESTCASES"

#: Directory name, relative to the repository root, that EPA's archive is
#: unpacked into (gitignored).
DEFAULT_ROOT_NAME = "test_cases"

# aermet_24142_aermod_24142  /  aermet24142_aermod26135
_SET_NAME_RE = re.compile(r"^aermet_?(\d{5})_aermod_?(\d{5})$", re.IGNORECASE)
# " *** AERMOD - VERSION 26135  ***" (header of every .out/.SUM/.PST)
_BANNER_RE = re.compile(r"AERMOD\s*-\s*VERSION\s+(\d{5})")
# " Usage: AERMOD 26135  takes either no or one or two parameters."
_USAGE_RE = re.compile(r"AERMOD\s+(\d{5})\b")


@dataclass(frozen=True)
class EPATestCaseSet:
    """One EPA reference set (a ``aermet<M>_aermod<A>`` directory).

    Parameters
    ----------
    path : Path
        Directory of the set.
    aermet_version : str, optional
        Five-digit AERMET version (``"24142"``) parsed from the directory
        name; ``None`` if the name does not carry one.
    aermod_version : str, optional
        Five-digit AERMOD version parsed from the directory name, or
        from the banner of a file in ``Outputs/`` when the name does not
        carry one.
    """

    path: Path
    aermet_version: Optional[str] = None
    aermod_version: Optional[str] = None

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def inputs(self) -> Path:
        return self.path / "inputs"

    @property
    def meteorology(self) -> Path:
        return self.path / "meteorology"

    @property
    def postfiles(self) -> Path:
        return self.path / "postfiles"

    @property
    def plotfiles(self) -> Path:
        return self.path / "plotfiles"

    @property
    def outputs(self) -> Path:
        return self.path / "Outputs"

    def exists(self) -> bool:
        """True if the set has the ``inputs/`` and ``postfiles/`` trees."""
        return self.inputs.is_dir() and self.postfiles.is_dir()

    def describe(self) -> str:
        """Human-readable label, e.g. ``aermet26135_aermod26135 (AERMET 26135, AERMOD 26135)``."""
        return (
            f"{self.name} (AERMET {self.aermet_version or '?'}, "
            f"AERMOD {self.aermod_version or '?'})"
        )


def parse_aermod_version(text: str) -> Optional[str]:
    """Return the five-digit AERMOD version found in `text`, if any.

    Recognises both the ``*** AERMOD - VERSION NNNNN ***`` banner that
    heads every AERMOD output file and the ``Usage: AERMOD NNNNN``
    line the binary prints for ``--help``.
    """
    m = _BANNER_RE.search(text) or _USAGE_RE.search(text)
    return m.group(1) if m else None


def read_aermod_version(path: Union[str, Path], max_bytes: int = 8192) -> Optional[str]:
    """Parse the AERMOD version banner from the head of an output file.

    AERMOD writes Latin-1; the file is decoded leniently so a stray byte
    can never hide the banner. Returns ``None`` if the file cannot be
    read or carries no banner in its first `max_bytes`.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(max_bytes)
    except OSError:
        return None
    return parse_aermod_version(head.decode("latin-1", errors="replace"))


def aermod_binary_version(
    executable: Optional[Union[str, Path]] = None,
    timeout: float = 30.0,
) -> Optional[str]:
    """Return the version of an AERMOD binary by running ``aermod --help``.

    Parameters
    ----------
    executable : str or Path, optional
        Binary to probe; defaults to ``aermod`` on ``PATH``.
    timeout : float
        Seconds to wait for the probe before giving up.

    Returns
    -------
    str or None
        Five-digit version (``"26135"``), or ``None`` if no binary was
        found, it could not be run, or its output carried no version.

    Notes
    -----
    The probe runs in a throw-away directory because AERMOD drops a
    ``--help_ERRMSG.TMP`` file in its working directory.
    """
    exe = executable or shutil.which("aermod")
    if exe is None:
        return None
    with tempfile.TemporaryDirectory(prefix="pyaermod_version_probe_") as tmp:
        try:
            proc = subprocess.run(
                [str(exe), "--help"],
                cwd=tmp,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
    return parse_aermod_version((proc.stdout or "") + (proc.stderr or ""))


def describe_set(path: Union[str, Path]) -> EPATestCaseSet:
    """Build an :class:`EPATestCaseSet` for `path`.

    Versions come from the directory name when it follows EPA's
    ``aermet<M>_aermod<A>`` convention (either spelling); otherwise the
    AERMOD version is read from the banner of the first ``.out``/``.SUM``
    file in ``Outputs/``.
    """
    p = Path(path)
    m = _SET_NAME_RE.match(p.name)
    if m:
        return EPATestCaseSet(p, aermet_version=m.group(1), aermod_version=m.group(2))
    aermod: Optional[str] = None
    outputs = p / "Outputs"
    if outputs.is_dir():
        for f in sorted(outputs.iterdir()):
            if f.suffix.lower() in (".out", ".sum"):
                aermod = read_aermod_version(f)
                if aermod:
                    break
    return EPATestCaseSet(p, aermet_version=None, aermod_version=aermod)


def list_epa_testcase_sets(root: Union[str, Path]) -> List[EPATestCaseSet]:
    """All ``aermet*_aermod*`` directories under `root`, sorted by name.

    Both naming conventions are accepted. Missing `root` yields ``[]``.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []
    out: List[EPATestCaseSet] = []
    for p in sorted(root_path.iterdir()):
        lowered = p.name.lower()
        if p.is_dir() and lowered.startswith("aermet") and "aermod" in lowered:
            out.append(describe_set(p))
    return out


def _newest_key(s: EPATestCaseSet):
    return (int(s.aermod_version or 0), int(s.aermet_version or 0), s.name)


def find_epa_testcase_set(
    root: Optional[Union[str, Path]] = None,
    *,
    aermod_version: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> Optional[EPATestCaseSet]:
    """Pick the EPA reference set to test against.

    Parameters
    ----------
    root : str or Path, optional
        Directory holding the unpacked sets; defaults to
        ``<cwd>/test_cases``.
    aermod_version : str, optional
        Prefer a set whose references were produced by this AERMOD
        version (e.g. the output of :func:`aermod_binary_version`). If
        no set matches, the selection falls through to the validated-
        version preference and then the newest set — callers that care
        should compare ``result.aermod_version`` themselves.
    env : mapping, optional
        Environment to consult for :data:`ENV_VAR`; defaults to
        ``os.environ``.

    Returns
    -------
    EPATestCaseSet or None
        ``None`` when no set is present (and the environment override is
        unset). When the override *is* set, it is returned as given even
        if the directory is missing, so callers can report the bad path
        rather than silently testing something else.
    """
    environ = os.environ if env is None else env
    override = environ.get(ENV_VAR)
    if override:
        return describe_set(Path(override).expanduser().resolve())

    root_path = Path(root) if root is not None else Path.cwd() / DEFAULT_ROOT_NAME
    sets = [s for s in list_epa_testcase_sets(root_path) if s.exists()]
    if not sets:
        return None
    if aermod_version:
        matching = [s for s in sets if s.aermod_version == str(aermod_version)]
        if matching:
            return max(matching, key=_newest_key)
    # No usable hint: prefer the newest *validated* release (26135 over
    # 24142) before falling back to whatever is newest on disk.
    for validated in VALIDATED_AERMOD_VERSIONS:
        matching = [s for s in sets if s.aermod_version == validated]
        if matching:
            return max(matching, key=_newest_key)
    return max(sets, key=_newest_key)


__all__ = [
    "DEFAULT_ROOT_NAME",
    "ENV_VAR",
    "EPATestCaseSet",
    "aermod_binary_version",
    "describe_set",
    "find_epa_testcase_set",
    "list_epa_testcase_sets",
    "parse_aermod_version",
    "read_aermod_version",
]

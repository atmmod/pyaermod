"""
EPA model versions pyaermod is validated against.

"Validated" has a specific, reproducible meaning here:

* **AERMOD** — a gfortran build of that EPA release, driven by
  :class:`pyaermod.runner.AERMODRunner`, reproduces EPA's published
  AERTEST plotfile bit-for-bit (``tests/test_real_aermod.py``) **and**
  every POSTFILE in EPA's test-case suite for that release scores within
  EPA's own ±0.001 best-fit-slope margin (``tests/regulatory/`` and
  ``scripts/run_epa_parity.py``; results in ``docs/validation.md``).
* **AERMET** — pyaermod's ``.SFC``/``.PFL`` readers parse every file in
  EPA's AERMET test-case outputs for that release
  (``tests/test_real_aermet.py``), and the AERMOD parity suite above is
  driven with meteorology produced by that AERMET release.

The tuples are ordered newest-first; the first entry is the release the
project currently targets. Older entries remain supported for
cross-version regression (EPA publishes reference sets for both), not
merely "known to exist". Output parsers warn once when they meet a
version outside these tuples — the format may still parse fine, but it
has not been checked.

AERMAP is versioned separately by EPA and is not covered by these tuples.
"""

from __future__ import annotations

#: AERMOD releases validated as described in the module docstring, newest first.
VALIDATED_AERMOD_VERSIONS: tuple[str, ...] = ("26135", "24142")

#: AERMET releases validated as described in the module docstring, newest first.
VALIDATED_AERMET_VERSIONS: tuple[str, ...] = ("26135", "24142")


def is_validated_aermod_version(version: str | None) -> bool:
    """True if `version` (a five-digit AERMOD version string) is validated."""
    return version is not None and str(version).strip() in VALIDATED_AERMOD_VERSIONS


def is_validated_aermet_version(version: str | None) -> bool:
    """True if `version` (a five-digit AERMET version string) is validated."""
    return version is not None and str(version).strip() in VALIDATED_AERMET_VERSIONS


__all__ = [
    "VALIDATED_AERMET_VERSIONS",
    "VALIDATED_AERMOD_VERSIONS",
    "is_validated_aermet_version",
    "is_validated_aermod_version",
]

"""
Units and help text for the fields of the library's dataclasses.

A field that carries them is declared with
``field(default=..., metadata=described("m", "Stack height above ..."))``;
readers such as the GUI's form helper look them up with :func:`units_of`
and :func:`help_of`. The text says what AERMOD does with the value, in
the words of the user's guide, so a form can show it beside the input.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, Optional

#: The metadata keys.
UNITS = "units"
HELP = "help"


def described(units: Optional[str], help: str) -> Dict[str, str]:
    """Field metadata naming the value's units (``""`` for none) and what it is.

    ``units`` is ``None`` for a value that is not a quantity (a name, a
    file, a switch) and ``""`` for a count or a ratio.
    """
    meta = {HELP: help}
    if units is not None:
        meta[UNITS] = units
    return meta


def _metadata(fmeta: Any) -> Any:
    return getattr(fmeta, "metadata", None) or {}


def units_of(fmeta: dataclasses.Field) -> Optional[str]:
    """The units recorded on a dataclass field, or None."""
    return _metadata(fmeta).get(UNITS)


def help_of(fmeta: dataclasses.Field) -> Optional[str]:
    """The help text recorded on a dataclass field, or None."""
    return _metadata(fmeta).get(HELP)


__all__ = ["HELP", "UNITS", "described", "help_of", "units_of"]

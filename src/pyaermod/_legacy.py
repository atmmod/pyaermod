"""Helpful errors for dataclass field names that were renamed or removed."""

import functools
from typing import Any, Dict


def install_legacy_check(cls: type, renamed: Dict[str, str], removed: Dict[str, str], note: str) -> None:
    """Make ``cls(...)`` raise a TypeError that names the replacement for an old field.

    ``renamed`` maps an old field name to the new one, ``removed`` maps an
    old field name to why it has no replacement, and ``note`` ends the
    message for a renamed field.

    The dataclass generates __init__, so the check has to wrap it rather
    than live in __post_init__ (which never sees an unexpected keyword:
    __init__ has already raised by then).
    """
    generated_init = cls.__init__  # type: ignore[misc]

    @functools.wraps(generated_init)
    def init_with_legacy_check(self: Any, *args: Any, **kwargs: Any) -> None:
        for old, new in renamed.items():
            if old in kwargs:
                raise TypeError(f"{cls.__name__} has no field {old!r}; it is now {new!r}. {note}")
        for old, why in removed.items():
            if old in kwargs:
                raise TypeError(f"{cls.__name__} has no field {old!r}. {why}")
        generated_init(self, *args, **kwargs)

    cls.__init__ = init_with_legacy_check  # type: ignore[misc]

"""
Shared optional-dependency helpers.

Replaces per-module duplicated `try: import X; HAS_X = True; except ...`
and ad-hoc `_require_X()` guards with a single pattern:

    from ._optional import optional_import, require

    requests = optional_import("requests")
    pandas = optional_import("pandas", pip_extra="viz")

    def fetch(...):
        require(requests, "requests", pip_extra="met")
        ...

Usage notes
-----------
- `optional_import(name)` returns the imported module or `None` if
  unavailable — it never raises at import time.
- `require(module, name, pip_extra=...)` raises ImportError with a
  helpful install hint if the module is None.
- A module object is truthy; `None` is falsy — so existing `if HAS_X:`
  patterns become `if module:`.
- For packaging compatibility, each module that used to export
  `HAS_X` can keep doing so; just assign `HAS_X = bool(module)`.
"""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Optional


def optional_import(name: str) -> Optional[ModuleType]:
    """Import `name` and return the module, or None if unavailable.

    Swallows ImportError (missing package) and the common numpy/pandas
    binary-incompatibility AttributeError so pyaermod stays importable
    on misconfigured environments.
    """
    try:
        return importlib.import_module(name)
    except (ImportError, AttributeError):
        return None


def require(module: Optional[ModuleType], name: str,
            *, pip_extra: Optional[str] = None) -> ModuleType:
    """Assert `module` is non-None or raise a helpful ImportError.

    Use at the top of any function that needs the optional dependency:

        def do_thing():
            require(requests, "requests", pip_extra="met")
            resp = requests.get(...)

    Parameters
    ----------
    module : module or None
        Result of `optional_import(name)`.
    name : str
        Human-readable package name (for the error message).
    pip_extra : str, optional
        pyaermod extras group that pulls this dep in, e.g. "met" or
        "geo". Included in the install-hint.
    """
    if module is not None:
        return module
    hint = f"pip install 'pyaermod[{pip_extra}]'" if pip_extra else f"pip install {name}"
    raise ImportError(
        f"{name} is required for this feature but is not installed. "
        f"Install with: {hint}"
    )


__all__ = ["optional_import", "require"]

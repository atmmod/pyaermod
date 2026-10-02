"""Reading numbers as AERMOD's Fortran writes them.

Fortran ``Ew.d`` editing writes the exponent as ``E`` and two digits
(``0.282465E-03``) when it fits in two digits, and as a sign and three
digits with no letter (``0.282465-103``) when it does not; that is the
standard's rule for ``Ew.d`` without ``Ee``. AERMOD's ``OU FILEFORM
EXP`` output (``E13.6``, ``E14.6`` in the summary tables, an EVENT
run's source contributions included, ``E17.6`` in the ``EVENTPER``
cards of an ``EVENTFIL``) therefore prints a value below 1e-99 in the
second form, which Python's :func:`float` refuses.
"""

from __future__ import annotations

import re

# A mantissa with a decimal point, then the exponent's sign and three
# digits. Ew.d always writes the decimal point, and only an exponent
# from 100 to 999 is written without the E, so anything else (one or
# two exponent digits, no point, a second sign) is not a number.
_E_FREE_EXPONENT = re.compile(r"([+-]?(?:\d+\.\d*|\.\d+))([+-]\d{3})")


def fortran_float(text: str) -> float:
    """``text`` as a float, accepting Fortran's E-free three-digit exponent.

    Everything :func:`float` reads is read the same way; in addition
    ``"0.282465-103"`` is ``2.82465e-104`` and ``"0.1+101"`` is
    ``1e100``. Anything else raises :class:`ValueError`, as
    :func:`float` does.
    """
    try:
        return float(text)
    except ValueError:
        match = _E_FREE_EXPONENT.fullmatch(text.strip())
        if match is None:
            raise
    return float(f"{match.group(1)}E{match.group(2)}")

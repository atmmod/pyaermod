"""Reading numbers as AERMOD's Fortran writes and reads them.

Fortran ``Ew.d`` editing writes the exponent as ``E`` and two digits
(``0.282465E-03``) when it fits in two digits, and as a sign and three
digits with no letter (``0.282465-103``) when it does not; that is the
standard's rule for ``Ew.d`` without ``Ee``. AERMOD's ``OU FILEFORM
EXP`` output (``E13.6``, ``E14.6`` in the summary tables, an EVENT
run's source contributions included, ``E17.6`` in the ``EVENTPER``
cards of an ``EVENTFIL``) therefore prints a value below 1e-99 in the
second form, which Python's :func:`float` refuses.

A runstream field AERMOD reads with setup.f STODBL may also carry a
Fortran ``D`` exponent (``3.6D6``, as EPA's testpart deck has it), which
:func:`float` refuses too. STODBL reads no ``NaN``, ``Infinity`` or
``1_000``, all of which :func:`float` does read.
"""

from __future__ import annotations

import re

# A decimal number with an optional E or D exponent, in ASCII digits
# only: float() also reads NaN, infinities, digit-group underscores and
# non-ASCII digits, none of which Fortran writes or STODBL reads.
_DECIMAL = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[EeDd][+-]?\d+)?", re.ASCII)

# A mantissa with a decimal point, then the exponent's sign and three
# digits. Ew.d always writes the decimal point, and only an exponent
# from 100 to 999 is written without the E, so anything else (one or
# two exponent digits, no point, a second sign) is not a number.
_E_FREE_EXPONENT = re.compile(r"([+-]?(?:\d+\.\d*|\.\d+))([+-]\d{3})", re.ASCII)


def fortran_float(text: str) -> float:
    """``text`` as a float, read as Fortran writes numbers and STODBL reads them.

    A decimal number, with an optional exponent after ``E`` or ``D``
    (``"3.6D6"`` is ``3.6e6``), or Fortran's E-free three-digit exponent
    (``"0.282465-103"`` is ``2.82465e-104``, ``"0.1+101"`` is ``1e100``).
    Surrounding whitespace is ignored. Anything else raises
    :class:`ValueError`, including what only Python's :func:`float`
    reads: ``nan``, ``inf``/``infinity``, ``1_000`` and non-ASCII digits.
    """
    stripped = text.strip()
    if _DECIMAL.fullmatch(stripped):
        return float(stripped.replace("D", "E").replace("d", "e"))
    match = _E_FREE_EXPONENT.fullmatch(stripped)
    if match is None:
        raise ValueError(f"could not convert string to float: {text!r}")
    return float(f"{match.group(1)}E{match.group(2)}")

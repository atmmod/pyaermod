"""
EPA AERMOD test-suite parity helpers.

Used to score a pyaermod-produced POSTFILE against an EPA reference
POSTFILE from the bundled AERMOD test-case distribution
(``test_cases/aermet_24142_aermod_24142/postfiles/*.PST``).

The scoring metric is the **best-fit slope** of paired
(reference, candidate) concentrations through the origin, matching
EPA's ``Compare_AERMOD_test_cases.R`` script. The script's published
acceptance margin is ±0.001 around 1.0; we expose that as
:data:`DEFAULT_SLOPE_TOLERANCE` and the convenience predicate
:func:`passes_parity`.

Pairing is done on (x, y, date, ave, grp) join keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Union

import pandas as pd

from .postfile import read_postfile

#: EPA's published margin of error on best-fit slope (Compare_AERMOD_test_cases.R).
DEFAULT_SLOPE_TOLERANCE: float = 0.001


@dataclass
class ParityScore:
    """Outcome of comparing a candidate POSTFILE to an EPA reference."""
    case: str
    n_paired: int
    slope: float            # best-fit slope through origin: candidate ~ k * reference
    mean_abs_error: float   # mean |candidate - reference|
    norm_mean_error: float  # sum|delta| / sum(reference)  (NaN if sum=0)
    max_abs_error: float
    ref_max: float
    cand_max: float

    def passes(self, tolerance: float = DEFAULT_SLOPE_TOLERANCE) -> bool:
        """True if best-fit slope is within `tolerance` of 1.0."""
        return abs(self.slope - 1.0) <= tolerance


def _best_fit_slope_through_origin(ref: pd.Series, cand: pd.Series) -> float:
    """Slope k minimizing sum((cand - k*ref)**2): sum(ref*cand)/sum(ref**2)."""
    denom = float((ref * ref).sum())
    if denom == 0.0:
        return float("nan")
    return float((ref * cand).sum() / denom)


def score_postfile_pair(
    reference: Union[str, Path],
    candidate: Union[str, Path],
    *,
    case: str = "",
) -> ParityScore:
    """
    Score a candidate POSTFILE against an EPA reference POSTFILE.

    Both files must be in the same format (PLOT or UNFORM); the auto-detect
    in :func:`pyaermod.postfile.read_postfile` is applied to each.

    Pairing is on (x, y, date, ave, grp). Receptors / timesteps that
    appear in only one file are dropped before scoring (their count is
    not subtracted from `n_paired`).
    """
    ref_res = read_postfile(reference)
    cand_res = read_postfile(candidate)
    keys = ["x", "y", "date", "ave", "grp"]
    merged = ref_res.data.merge(
        cand_res.data, on=keys, how="inner", suffixes=("_ref", "_cand"),
    )
    if merged.empty:
        return ParityScore(
            case=case, n_paired=0, slope=float("nan"),
            mean_abs_error=float("nan"), norm_mean_error=float("nan"),
            max_abs_error=float("nan"),
            ref_max=ref_res.max_concentration,
            cand_max=cand_res.max_concentration,
        )
    ref = merged["concentration_ref"]
    cand = merged["concentration_cand"]
    delta = (cand - ref).abs()
    ref_sum = float(ref.sum())
    return ParityScore(
        case=case,
        n_paired=len(merged),
        slope=_best_fit_slope_through_origin(ref, cand),
        mean_abs_error=float(delta.mean()),
        norm_mean_error=float(delta.sum() / ref_sum) if ref_sum else float("nan"),
        max_abs_error=float(delta.max()),
        ref_max=ref_res.max_concentration,
        cand_max=cand_res.max_concentration,
    )


def passes_parity(
    reference: Union[str, Path],
    candidate: Union[str, Path],
    *,
    tolerance: float = DEFAULT_SLOPE_TOLERANCE,
) -> bool:
    """Convenience: True if the candidate's best-fit slope is within tolerance."""
    return score_postfile_pair(reference, candidate).passes(tolerance)


__all__ = [
    "DEFAULT_SLOPE_TOLERANCE",
    "ParityScore",
    "passes_parity",
    "score_postfile_pair",
]

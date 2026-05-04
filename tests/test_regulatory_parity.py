"""Unit tests for regulatory_parity scoring helpers.

Uses synthetic PLOT-format POSTFILE strings (no EPA fixtures needed)
so it can run in any CI environment.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.regulatory_parity import (
    DEFAULT_SLOPE_TOLERANCE,
    ParityScore,
    passes_parity,
    score_postfile_pair,
)

_HEADER = (
    "* AERMOD (24142 ): synthetic                                12/03/24\n"
    "* AERMET ( 24142):                                          12:00:00\n"
    "* MODELING OPTIONS USED:   CONC  FLAT  RURAL\n"
    "*         POST/PLOT FILE OF CONCURRENT  1-HR VALUES FOR SOURCE GROUP: ALL\n"
    "*         FOR A TOTAL OF     3 RECEPTORS.\n"
    "*         FORMAT: (3(1X,F13.5),3(1X,F8.2),2X,A6,2X,A8,2X,I8.8,2X,A8)\n"
    "*        X             Y      AVERAGE CONC    ZELEV    ZHILL    ZFLAG"
    "    AVE     GRP       DATE     NET ID\n"
    "* ____________  ____________  ____________   ______   ______   ______"
    "  ______  ________  ________  ________\n"
)


def _row(x: float, y: float, conc: float) -> str:
    return (
        f" {x:13.5f} {y:13.5f} {conc:13.5f}"
        f"     0.00     0.00     0.00    1-HR  ALL       88030101  POL1\n"
    )


def _write_pst(path: Path, rows: list[tuple[float, float, float]]) -> None:
    path.write_text(_HEADER + "".join(_row(*r) for r in rows), encoding="utf-8")


@pytest.fixture
def ref_pst(tmp_path):
    p = tmp_path / "ref.PST"
    _write_pst(p, [(100.0, 0.0, 1.0), (200.0, 0.0, 2.0), (300.0, 0.0, 4.0)])
    return p


def test_perfect_match_slope_is_one(ref_pst, tmp_path):
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 1.0), (200.0, 0.0, 2.0), (300.0, 0.0, 4.0)])
    score = score_postfile_pair(ref_pst, cand, case="perfect")
    assert score.n_paired == 3
    assert score.slope == pytest.approx(1.0, abs=1e-12)
    assert score.mean_abs_error == 0.0
    assert score.passes()


def test_uniform_2x_scaling_slope_is_two(ref_pst, tmp_path):
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 2.0), (200.0, 0.0, 4.0), (300.0, 0.0, 8.0)])
    score = score_postfile_pair(ref_pst, cand)
    assert score.slope == pytest.approx(2.0, abs=1e-9)
    assert not score.passes()


def test_within_default_tolerance(ref_pst, tmp_path):
    # Multiply by 1.0005 — within ±0.001 margin
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 1.0005),
                      (200.0, 0.0, 2.001),
                      (300.0, 0.0, 4.002)])
    score = score_postfile_pair(ref_pst, cand)
    assert abs(score.slope - 1.0) < DEFAULT_SLOPE_TOLERANCE
    assert score.passes()


def test_outside_default_tolerance_fails(ref_pst, tmp_path):
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 1.01), (200.0, 0.0, 2.02), (300.0, 0.0, 4.04)])
    score = score_postfile_pair(ref_pst, cand)
    assert not score.passes()
    # ~1% bias — well outside 0.001 margin


def test_passes_parity_convenience(ref_pst, tmp_path):
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 1.0), (200.0, 0.0, 2.0), (300.0, 0.0, 4.0)])
    assert passes_parity(ref_pst, cand) is True


def test_no_overlap_returns_nan(ref_pst, tmp_path):
    cand = tmp_path / "cand.PST"
    # Different receptor coords: no inner-join match
    _write_pst(cand, [(999.0, 0.0, 1.0), (888.0, 0.0, 2.0)])
    score = score_postfile_pair(ref_pst, cand)
    assert score.n_paired == 0
    assert score.slope != score.slope  # NaN
    assert not score.passes()


def test_score_carries_case_label(ref_pst, tmp_path):
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 1.0), (200.0, 0.0, 2.0), (300.0, 0.0, 4.0)])
    score = score_postfile_pair(ref_pst, cand, case="AERTEST_01H")
    assert score.case == "AERTEST_01H"
    assert isinstance(score, ParityScore)


def test_zero_reference_norm_error_is_nan(tmp_path):
    ref = tmp_path / "ref.PST"
    _write_pst(ref, [(100.0, 0.0, 0.0), (200.0, 0.0, 0.0)])
    cand = tmp_path / "cand.PST"
    _write_pst(cand, [(100.0, 0.0, 0.0), (200.0, 0.0, 0.0)])
    score = score_postfile_pair(ref, cand)
    # Both zero: slope undefined (denom=0), norm_mean_error undefined
    assert score.slope != score.slope  # NaN
    assert score.norm_mean_error != score.norm_mean_error  # NaN

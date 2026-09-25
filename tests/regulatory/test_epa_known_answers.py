"""Known-answer tests against the outputs EPA ships with its test cases.

The parity harness in ``test_epa_aermod_suite.py`` re-runs each deck and
compares the concentrations pyaermod's *inputs* produce. These tests ask
a different question, and need no AERMOD binary: given EPA's own
concentration time series, does pyaermod's **post-processing** -- the
ranking that every NAAQS design value is built on -- reproduce EPA's own
ranked tables?

Three anchors, all from files in the reference set:

``postfiles/*.PST``
    Concurrent values: every receptor, every averaging period. The input.
``plotfiles/*.PLT`` and ``Outputs/*.DA[1-8]``
    AERMOD's ``RECTABLE`` answer: the n-th highest value *at each
    receptor*, with the date it occurred.
``Outputs/*.SUM``
    AERMOD's ``MAXTABLE`` answer: for rank n, the largest n-th-highest
    value anywhere in the domain, with its receptor.

A mismatch here is a defect in pyaermod's ranking, not a model
difference: both sides are derived from the identical concentration
values in the .PST.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pyaermod.aermod_outputs import read_plotfile
from pyaermod.design_values import nth_highest_daily_max_design_value
from pyaermod.postfile import read_postfile

from .conftest import (
    EPA_TESTCASE_DIR,
    missing_reason,
    reference_outputs_ready,
)

pytestmark = pytest.mark.skipif(
    not reference_outputs_ready(), reason=missing_reason()
)

# Reading and ranking runs at roughly 60 MB/s, so the handful of very
# large decks are marked slow rather than dropped -- ``-m slow`` runs
# them. Nothing is silently excluded: every pair EPA ships is collected.
_SLOW_BYTES = 20 * 1024 * 1024


def _plotfile_kind(path: Path) -> str:
    """``"design_value"`` for a NAAQS-form plotfile, else ``"rank"``.

    With ``POLLUTID NO2`` and a 1-hour averaging period AERMOD switches
    on its 1-hour NO2 NAAQS processing, and the PLOTFILE then holds
    ``1ST-HIGHEST MAX DAILY 1-HR VALUES AVERAGED OVER n YEARS`` -- the
    design value -- rather than the plain 1st-highest hourly value.
    """
    header = path.read_text(encoding="latin-1", errors="replace")[:2000]
    upper = header.upper()
    if "MAX DAILY" in upper and "AVERAGED OVER" in upper:
        return "design_value"
    if "1ST HIGH" in upper:
        return "rank"
    return "other"


def _pst_plt_pairs() -> tuple:
    """Split ``postfiles/X.PST`` + ``plotfiles/X.PLT`` pairs by kind."""
    plotdir = EPA_TESTCASE_DIR / "plotfiles"
    postdir = EPA_TESTCASE_DIR / "postfiles"
    if not (plotdir.is_dir() and postdir.is_dir()):
        return [], [], []
    ranks, design, other = [], [], []
    for plt in sorted(plotdir.glob("*.PLT")):
        pst = postdir / f"{plt.stem}.PST"
        if not pst.is_file():
            continue
        kind = _plotfile_kind(plt)
        # The two design-value pairs are the only EPA-authored check of
        # the NAAQS algorithm itself, so they run by default whatever
        # their size (about 1.7 s each). Only the bulk rank-1 pairs get
        # deferred when the .PST is very large.
        marks = (
            [pytest.mark.slow]
            if kind == "rank" and pst.stat().st_size > _SLOW_BYTES
            else []
        )
        param = pytest.param(plt.stem, marks=marks, id=plt.stem)
        {"rank": ranks, "design_value": design}.get(kind, other).append(param)
    return ranks, design, other


PST_PLT_PAIRS, PST_PLT_DESIGN_VALUE_PAIRS, PST_PLT_UNCLASSIFIED = (
    _pst_plt_pairs()
)


def _receptor_rank(df: pd.DataFrame, rank: int) -> pd.DataFrame:
    """Per-receptor ``rank``-th highest concentration.

    Exactly-repeated rows are dropped first: a deck may declare the same
    receptor twice (EPA's ``surfcoal`` does), and without the drop the
    second-highest value is a copy of the highest.
    """
    dedup = df.drop_duplicates(subset=["x", "y", "date", "concentration"])
    return (
        dedup.groupby(["x", "y"], as_index=False, sort=False)["concentration"]
        .agg(lambda s: np.sort(s.to_numpy())[-rank] if len(s) >= rank
             else np.nan)
    )


def _plotfile_frame(path: Path) -> pd.DataFrame:
    """``x, y, concentration`` from a PLOTFILE, one row per receptor."""
    res = read_plotfile(path)
    frame = pd.DataFrame(res.records)
    conc_col = res.concentration_column
    assert conc_col, f"no concentration column in {path}: {res.column_names}"
    out = frame.rename(
        columns={"X": "x", "Y": "y", conc_col: "concentration"}
    )[["x", "y", "concentration"]]
    return out.drop_duplicates()


def _assert_ranks_match(computed: pd.DataFrame, reference: pd.DataFrame,
                        label: str) -> None:
    merged = reference.merge(
        computed, on=["x", "y"], how="outer",
        suffixes=("_epa", "_pyaermod"), indicator=True,
    )
    unmatched = merged[merged["_merge"] != "both"]
    assert unmatched.empty, (
        f"{label}: receptors present on only one side:\n{unmatched.head(10)}"
    )
    # Both sides come from the same .PST values written to five decimals,
    # so agreement is exact; a tolerance would hide a real ranking error.
    diff = (merged["concentration_epa"] - merged["concentration_pyaermod"]).abs()
    worst = diff.max()
    assert worst == 0.0, (
        f"{label}: {int((diff > 0).sum())} of {len(merged)} receptors "
        f"differ, worst {worst:g}:\n"
        f"{merged[diff > 0].head(10)}"
    )


# ---------------------------------------------------------------------
# 1. Every PST/PLT pair: the 1st-highest value at every receptor
# ---------------------------------------------------------------------

@pytest.mark.epa
@pytest.mark.parametrize("stem", PST_PLT_PAIRS)
def test_first_high_matches_epa_plotfile(stem, epa_reference_set):
    pst = epa_reference_set / "postfiles" / f"{stem}.PST"
    plt = epa_reference_set / "plotfiles" / f"{stem}.PLT"
    data = read_postfile(pst).data
    _assert_ranks_match(
        _receptor_rank(data, 1), _plotfile_frame(plt), f"{stem} rank 1",
    )


def test_the_pair_set_is_not_empty():
    """Guard against a resolver change silently collecting nothing."""
    assert len(PST_PLT_PAIRS) >= 40, (
        f"only {len(PST_PLT_PAIRS)} PST/PLT pairs found under "
        f"{EPA_TESTCASE_DIR}; the known-answer suite would pass vacuously"
    )
    assert not PST_PLT_UNCLASSIFIED, (
        "PST/PLT pairs whose plotfile header matched no known form, so "
        "nothing checks them: "
        f"{[p.id for p in PST_PLT_UNCLASSIFIED]}"
    )


# ---------------------------------------------------------------------
# 1b. The NAAQS design-value form, straight from AERMOD
# ---------------------------------------------------------------------

@pytest.mark.epa
@pytest.mark.parametrize("stem", PST_PLT_DESIGN_VALUE_PAIRS)
def test_design_value_matches_epa_naaqs_plotfile(stem, epa_reference_set):
    """``nth_highest_daily_max_design_value`` vs AERMOD's own answer.

    These plotfiles are what AERMOD writes under its 1-hour NO2 NAAQS
    processing: rank the maximum daily 1-hour value in each year, then
    average those annual values across the years modelled. That is the
    whole design-value algorithm, so agreeing with it receptor-by-
    receptor is the strongest evidence available that pyaermod computes
    the regulatory form and not merely a plausible statistic.
    """
    pst = epa_reference_set / "postfiles" / f"{stem}.PST"
    plt = epa_reference_set / "plotfiles" / f"{stem}.PLT"
    header = plt.read_text(encoding="latin-1", errors="replace")[:2000]
    rank_match = re.search(r"(\d+)(?:ST|ND|RD|TH)-HIGHEST", header, re.I)
    years_match = re.search(r"AVERAGED OVER\s+(\d+)\s+YEARS", header, re.I)
    assert rank_match and years_match, header
    rank = int(rank_match.group(1))
    n_years = int(years_match.group(1))

    data = read_postfile(pst).data
    computed = nth_highest_daily_max_design_value(
        data, rank=rank, daily="max", n_years=n_years,
    )
    assert computed["n_years"].iloc[0] == n_years
    _assert_ranks_match(
        computed[["x", "y", "concentration"]],
        _plotfile_frame(plt),
        f"{stem} design value (H{rank}H over {n_years} yr)",
    )


# ---------------------------------------------------------------------
# 2. surfcoal: ranks 1 through 8 of the 24-hour series
# ---------------------------------------------------------------------
#
# EPA's ``surfcoal`` deck writes a 24-hour POSTFILE plus eight separate
# PLOTFILEs, one per rank (``PLOTFILE 24 ALL 1ST`` ... ``8TH``). That is
# the depth the 98th-percentile forms need: the NO2 and PM2.5 design
# values are the 8th-highest daily value of a full year.

SURFCOAL_RANKS = list(range(1, 9))


@pytest.mark.epa
@pytest.mark.parametrize("rank", SURFCOAL_RANKS)
def test_surfcoal_24hr_ranks_one_through_eight(rank, epa_reference_set):
    pst = epa_reference_set / "postfiles" / "PSET2PA.PST"
    ref = epa_reference_set / "Outputs" / f"PSET2PA.DA{rank}"
    if not (pst.is_file() and ref.is_file()):
        pytest.skip(f"surfcoal 24-hour rank files not in {epa_reference_set}")
    data = read_postfile(pst).data
    assert (data["ave"].str.strip().str.upper() == "24-HR").all()
    _assert_ranks_match(
        _receptor_rank(data, rank), _plotfile_frame(ref),
        f"surfcoal 24-hour rank {rank}",
    )


def test_surfcoal_duplicate_receptor_is_really_duplicated(epa_reference_set):
    """Pin the condition the dedup in ``_receptor_rank`` exists for.

    If EPA ever ships this deck without the repeated receptor, the
    rank-2..8 tests above would keep passing while no longer exercising
    the case that made them fail before the fix.
    """
    pst = epa_reference_set / "postfiles" / "PSET2PA.PST"
    if not pst.is_file():
        pytest.skip("surfcoal 24-hour postfile not present")
    data = read_postfile(pst).data
    per_period = data.groupby(["x", "y", "date"]).size()
    assert (per_period > 1).any(), (
        "surfcoal no longer lists a receptor twice; the de-duplication "
        "path in the design-value code is now untested by this deck"
    )


# ---------------------------------------------------------------------
# 3. The .SUM overall-maximum table
# ---------------------------------------------------------------------
#
# ``*** THE SUMMARY OF HIGHEST 1-HR RESULTS ***`` lists, for rank n, the
# largest n-th-highest value at any receptor -- not the n-th largest
# value in the record. The distinction matters: on AERTEST the 2nd row
# is 421.98845, while the 2nd largest hourly value in the .PST is
# 746.09714 at a different receptor.

def _sum_ranked_rows(path: Path) -> list:
    """``(rank, concentration, x, y)`` from a SUM short-term table."""
    import re

    text = path.read_text(encoding="latin-1", errors="replace")
    start = text.upper().find("SUMMARY OF HIGHEST  1-HR RESULTS")
    if start < 0:
        return []
    section = text[start:]
    pattern = re.compile(
        r"HIGH\s+(\d+)(?:ST|ND|RD|TH)\s+HIGH VALUE IS\s+([-\d.E+]+)\s+"
        r"ON\s+\S+:\s+AT\s*\(\s*([-\d.E+]+),\s*([-\d.E+]+),",
        re.IGNORECASE,
    )
    rows = []
    for m in pattern.finditer(section):
        rows.append(
            (int(m.group(1)), float(m.group(2)),
             float(m.group(3)), float(m.group(4)))
        )
        if len(rows) >= 3:
            break
    return rows


@pytest.mark.epa
def test_aertest_sum_maxtable_matches_overall_nth_highest(epa_reference_set):
    sum_file = epa_reference_set / "Outputs" / "AERTEST.SUM"
    pst = epa_reference_set / "postfiles" / "AERTEST_01H.PST"
    if not (sum_file.is_file() and pst.is_file()):
        pytest.skip(f"AERTEST reference outputs not in {epa_reference_set}")

    rows = _sum_ranked_rows(sum_file)
    assert rows, f"no ranked 1-HR rows parsed from {sum_file}"

    data = read_postfile(pst).data
    for rank, conc, x, y in rows:
        per_receptor = _receptor_rank(data, rank)
        best = per_receptor.loc[per_receptor["concentration"].idxmax()]
        assert best["concentration"] == pytest.approx(conc, abs=1e-5), (
            f"rank {rank}: EPA {conc}, pyaermod {best['concentration']}"
        )
        # The .SUM prints coordinates to two decimals.
        assert round(float(best["x"]), 2) == pytest.approx(x, abs=0.01)
        assert round(float(best["y"]), 2) == pytest.approx(y, abs=0.01)

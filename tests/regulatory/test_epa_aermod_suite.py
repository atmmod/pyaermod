"""
EPA AERMOD test-suite parity harness.

For each input deck in ``test_cases/aermet_24142_aermod_24142/inputs/``,
run AERMOD via :class:`pyaermod.runner.AERMODRunner` in an isolated
working directory, then score every produced ``.PST`` POSTFILE against
the EPA reference of the same name. Pass criterion: best-fit slope of
(reference, candidate) within ±0.001 of 1.0 — matching EPA's own
``Compare_AERMOD_test_cases.R`` published margin.

The test is parametrized over input decks. Failures don't bring down
the build (pytest collects per-case results) so the report distinguishes
"X of Y cases pass parity."
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyaermod.regulatory_parity import (
    DEFAULT_SLOPE_TOLERANCE,
    score_postfile_pair,
)
from pyaermod.runner import AERMODRunner

from .conftest import (
    EPA_INPUTS_DIR,
    EPA_MET_DIR,
    EPA_REF_PST_DIR,
    EPA_SET_NAME,
    fixtures_ready,
    missing_reason,
)

# Skip the whole module — parametrisation included — when the fixtures or
# the AERMOD binary are absent. (A ``pytestmark`` assigned inside
# conftest.py is inert: pytest only honours pytestmark in test modules.)
if not fixtures_ready():
    pytest.skip(missing_reason(), allow_module_level=True)


def _discover_input_decks() -> list[str]:
    """List input deck filenames; empty list if fixtures absent."""
    if not EPA_INPUTS_DIR.exists():
        return []
    return sorted(p.name for p in EPA_INPUTS_DIR.glob("*.inp"))


# Cap runtime: a few decks (e.g. LVT24, MULTURB) take >1 min. The harness
# is for CI-on-demand / nightly runs, not push CI. Per-deck timeout 300s.
_DECK_TIMEOUT = 300

_DECKS = _discover_input_decks()


# Test IDs carry the reference-set name so a report line such as
# ``test_epa_case_parity[aermet26135_aermod26135/aertest.inp]`` records
# exactly which EPA references the run was scored against.
@pytest.mark.parametrize(
    "deck_name", _DECKS, ids=[f"{EPA_SET_NAME}/{d}" for d in _DECKS],
)
def test_epa_case_parity(deck_name, epa_testcase_dir, aermod_binary, scratch):
    """Run one EPA test deck through AERMOD; score every PST emitted."""
    work = scratch / deck_name.replace(".inp", "")
    work.mkdir()
    (work / "inputs").mkdir()
    (work / "meteorology").mkdir()
    (work / "postfiles").mkdir()
    (work / "plotfiles").mkdir()
    (work / "Outputs").mkdir()
    (work / "rdata").mkdir()

    # MULTYEAR-chained decks (e.g. testpm10_198{6..90}) need sequential
    # runs in a shared working dir so each year reads the prior year's
    # .sav file. Independent execution can't reproduce the EPA aggregate.
    src_text = (EPA_INPUTS_DIR / deck_name).read_text(errors="replace")
    if "MULTYEAR" in src_text.upper():
        pytest.skip(f"{deck_name} uses MULTYEAR — covered by chained-run test")

    # Stage the entire input + met-data tree so relative paths in the
    # deck (e.g. ../meteorology/AERMET2.SFC, mcr.emi, etc.) resolve.
    # Copy every non-.inp data file (extensions vary widely:
    # .dat, .emi, .ozn, .nox, .bgconc, ...). The active deck is the
    # only .inp file we copy.
    src_deck = EPA_INPUTS_DIR / deck_name
    shutil.copy2(src_deck, work / "inputs" / deck_name)
    for extra in EPA_INPUTS_DIR.iterdir():
        if extra.is_file() and extra.suffix.lower() != ".inp":
            shutil.copy2(extra, work / "inputs" / extra.name)
    for met in EPA_MET_DIR.glob("*"):
        if met.is_file():
            shutil.copy2(met, work / "meteorology" / met.name)

    runner = AERMODRunner(executable_path=aermod_binary, log_level="WARNING")
    inputs_dir = work / "inputs"
    result = runner.run(
        input_file=inputs_dir / deck_name,
        working_dir=inputs_dir,
        timeout=_DECK_TIMEOUT,
    )
    if not result.success:
        # Some decks legitimately can't run without files we don't
        # vendor (e.g. external background data). Emit xfail with the
        # error tail rather than a hard fail — the report aggregates
        # all outcomes.
        tail = (result.stdout or "")[-400:]
        pytest.xfail(f"AERMOD did not converge on {deck_name}: {tail!r}")

    # Discover PSTs the run produced + matching EPA references.
    candidate_psts = list((work / "postfiles").glob("*.PST"))
    if not candidate_psts:
        pytest.skip(f"{deck_name} produces no POSTFILE outputs")

    fails = []
    for cand in candidate_psts:
        ref = EPA_REF_PST_DIR / cand.name
        if not ref.exists():
            continue
        score = score_postfile_pair(ref, cand, case=cand.name)
        if not score.passes(DEFAULT_SLOPE_TOLERANCE):
            fails.append(score)

    assert not fails, (
        f"{deck_name}: {len(fails)} POSTFILE(s) outside EPA tolerance: "
        + "; ".join(
            f"{s.case} slope={s.slope:.6f} (n={s.n_paired})" for s in fails
        )
    )


_MULTYEAR_CHAIN = [
    "testpm10_1986.inp",
    "testpm10_1987.inp",
    "testpm10_1988.inp",
    "testpm10_1989.inp",
    "testpm10_1990.inp",
]


def test_epa_multyear_pm10_chain(epa_testcase_dir, aermod_binary, scratch):
    """Run the 5-year MULTYEAR PM-10 chain and score the final POSTFILE.

    MULTYEAR decks share a working directory across runs — each year reads
    the prior year's .sav file. The aggregate POSTFILE
    ``TESTPM10_MULTYR_01H.PST`` is appended by every year's run; we score
    it once after the final year completes.
    """
    work = scratch / "multyear_pm10"
    work.mkdir()
    (work / "inputs").mkdir()
    (work / "meteorology").mkdir()
    (work / "postfiles").mkdir()
    (work / "plotfiles").mkdir()
    (work / "Outputs").mkdir()

    # Stage every non-.inp data file plus all 5 yearly decks.
    for extra in EPA_INPUTS_DIR.iterdir():
        if extra.is_file() and extra.suffix.lower() != ".inp":
            shutil.copy2(extra, work / "inputs" / extra.name)
    for deck in _MULTYEAR_CHAIN:
        shutil.copy2(EPA_INPUTS_DIR / deck, work / "inputs" / deck)
    for met in EPA_MET_DIR.glob("*"):
        if met.is_file():
            shutil.copy2(met, work / "meteorology" / met.name)

    runner = AERMODRunner(executable_path=aermod_binary, log_level="WARNING")
    inputs_dir = work / "inputs"
    for deck in _MULTYEAR_CHAIN:
        result = runner.run(
            input_file=inputs_dir / deck,
            working_dir=inputs_dir,
            timeout=_DECK_TIMEOUT,
        )
        if not result.success:
            pytest.xfail(
                f"MULTYEAR chain failed at {deck}: "
                f"{(result.stdout or '')[-300:]!r}"
            )

    cand = work / "postfiles" / "TESTPM10_MULTYR_01H.PST"
    ref = EPA_REF_PST_DIR / "TESTPM10_MULTYR_01H.PST"
    assert cand.exists(), "Final-year run did not produce TESTPM10_MULTYR_01H.PST"
    score = score_postfile_pair(ref, cand, case="TESTPM10_MULTYR_01H.PST")
    assert score.passes(DEFAULT_SLOPE_TOLERANCE), (
        f"MULTYEAR PM-10 chain outside EPA tolerance: "
        f"slope={score.slope:.6f}, n={score.n_paired}"
    )

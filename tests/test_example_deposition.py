"""
examples/deposition_modeling.py writes decks that calculate deposition.

The example used to set only ``OutputPathway.output_type``, which
AERMOD has no use for, so its particle deck was a concentration-only
deck (``MODELOPT CONC FLAT DFAULT``) and its two gas decks failed
validation before they were written (GASDEPOS without ALPHA, E198);
``main()`` swallowed those errors. Which quantities AERMOD calculates
is decided by MODELOPT (coset.f, subroutine MODOPT), through the
ControlPathway ``calculate_*`` flags.

The first tests check each deck's MODELOPT and the keywords AERMOD
needs for it. The last runs every deck through the real AERMOD binary
(skipped when ``aermod`` is not on PATH), on four wet days of EPA's
Houston met (tests/fixtures/deposition_met), and checks that it
finishes, warns only about the placeholder SURFDATA/UAIRDATA, and gives
a non-zero PERIOD maximum for every quantity on MODELOPT.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from pyaermod import AERMODRunner

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "deposition_modeling.py"
MET = REPO / "tests" / "fixtures" / "deposition_met"
MET_STEM = "HOUSTON_1996-02-26_29"

# deck name -> (example function, MODELOPT tokens it must carry,
#               tokens it must not carry)
DECKS = {
    "gas_deposition.inp": (
        "example_1_gas_deposition",
        {"CONC", "DDEP", "ALPHA"},
        {"DFAULT"},  # ALPHA with DFAULT is E204
    ),
    "particle_deposition.inp": (
        "example_2_particle_deposition",
        {"CONC", "DEPOS", "DDEP", "WDEP", "FLAT"},
        {"DFAULT"},  # DFAULT overrides FLAT with ELEV (W206)
    ),
    "multi_source_deposition.inp": (
        "example_3_multi_source_groups",
        {"CONC", "DDEP", "ALPHA"},
        {"DFAULT"},
    ),
}
GAS_DECKS = ("gas_deposition.inp", "multi_source_deposition.inp")

# Column heading of each MODELOPT quantity in AERMOD's result tables
QUANTITY_LABEL = {
    "CONC": "AVERAGE CONC",
    "DEPOS": "TOTAL DEPO",
    "DDEP": "DRY DEPO",
    "WDEP": "WET DEPO",
}
# The only warnings a run of the example may give: the decks' SURFDATA
# and UAIRDATA are placeholders (station 0, year 2020), so AERMOD warns
# that they do not match the met file (W530) and takes the file's year
# (W492). Anything else, such as W206 (DFAULT overriding a non-DFAULT
# option) or W496 (no precipitation for wet deposition), fails the run.
ALLOWED_WARNINGS = {"W530", "W492"}


def _load_example():
    spec = importlib.util.spec_from_file_location("deposition_modeling", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cards(deck: str, keyword: str) -> list[list[str]]:
    """Fields after ``keyword`` on each of its cards in ``deck``."""
    out = []
    for line in deck.splitlines():
        fields = line.split()
        if fields and fields[0] == keyword:
            out.append(fields[1:])
    return out


@pytest.fixture(scope="module")
def decks(tmp_path_factory) -> Path:
    """Run the example's main() once in a scratch directory."""
    work = tmp_path_factory.mktemp("deposition_example")
    module = _load_example()
    mp = pytest.MonkeyPatch()
    mp.chdir(work)
    try:
        module.main()
    finally:
        mp.undo()
    return work


@pytest.mark.parametrize("deck_name", sorted(DECKS))
def test_example_writes_each_deck(decks, deck_name):
    # An empty or missing deck means its example raised: AERMODProject.write
    # opens the file before it validates, so a deck that fails validation
    # is left empty. main() now lets such errors through instead of
    # printing them and carrying on.
    deck = (decks / deck_name).read_text()
    assert deck.startswith("CO STARTING")


@pytest.mark.parametrize("deck_name", sorted(DECKS))
def test_deck_calculates_deposition_on_modelopt(decks, deck_name):
    _func, required, forbidden = DECKS[deck_name]
    deck = (decks / deck_name).read_text()
    (modelopt,) = _cards(deck, "MODELOPT")
    tokens = set(modelopt)
    assert required <= tokens, f"{deck_name}: MODELOPT {modelopt}"
    assert not (forbidden & tokens), f"{deck_name}: MODELOPT {modelopt}"


@pytest.mark.parametrize("deck_name", GAS_DECKS)
def test_gas_decks_carry_site_categories(decks, deck_name):
    # Gas dry deposition needs GDSEASON and GDLANUSE on CO, or AERMOD
    # stops with E244 DRYDEP (soset.f).
    deck = (decks / deck_name).read_text()
    (seasons,) = _cards(deck, "GDSEASON")
    (land_use,) = _cards(deck, "GDLANUSE")
    assert len(seasons) == 12
    assert len(land_use) == 36


def test_every_source_has_deposition_inputs(decks):
    # With DDEP on MODELOPT, AERMOD needs particle or gas deposition
    # inputs for every source (soset.f SRCQA, E242).
    deck = (decks / "multi_source_deposition.inp").read_text()
    sources = {fields[0] for fields in _cards(deck, "LOCATION")}
    with_inputs = {fields[0] for kw in ("GASDEPOS", "PARTDIAM") for fields in _cards(deck, kw)}
    assert sources == {"COMB1", "MATL1"}
    assert sources == with_inputs


def test_example_does_not_rely_on_output_type():
    # output_type selects nothing in AERMOD; the example must not set it.
    assert "output_type=" not in EXAMPLE.read_text()


def test_example_states_deposition_units():
    text = EXAMPLE.read_text()
    assert "g/m2/s" not in text
    assert "g/m**2/yr" in text


# Output types of each example deck -> fixture directory holding a real
# AERMOD v26135 run with those output types (tests/fixtures/postfile_types)
POSTFILE_FIXTURES = REPO / "tests" / "fixtures" / "postfile_types"
EXAMPLE_POSTFILE_RUNS = {
    ("CONC", "DDEP"): "conc_ddep",  # Examples 1 and 3
    ("CONC", "DEPOS", "DDEP", "WDEP"): "conc_depos_ddep_wdep",  # Example 2
}


def _stated_postfile_columns() -> list[list[str]]:
    """The POSTFILE column lists that Example 4's text prints, in order."""
    lists = re.findall(r"^\s*(\['x', 'y', [^\]]*\])\s*$", EXAMPLE.read_text(), flags=re.MULTILINE)
    return [re.findall(r"'([^']+)'", found) for found in lists]


def test_example_postfile_columns_match_the_reader():
    # Example 4 says which columns read_postfile gives for the POSTFILEs
    # of Examples 1-3; check that against real AERMOD POSTFILEs with the
    # same output types, so the text cannot drift from the reader again.
    from pyaermod.postfile import read_postfile

    deck_types = {frozenset(must & {"CONC", "DEPOS", "DDEP", "WDEP"}) for _, must, _ in DECKS.values()}
    assert deck_types == {frozenset(types) for types in EXAMPLE_POSTFILE_RUNS}

    stated = _stated_postfile_columns()
    assert len(stated) == len(EXAMPLE_POSTFILE_RUNS)
    for columns, (types, run) in zip(stated, EXAMPLE_POSTFILE_RUNS.items()):
        result = read_postfile(POSTFILE_FIXTURES / run / "post_1h.pst")
        assert result.output_types == types
        assert list(result.data.columns) == columns


def _warnings(out: str) -> set[str]:
    """Codes of the warnings in AERMOD's message summaries."""
    return set(re.findall(r"^ [A-Z]{2} (W\d{3}) ", out, flags=re.MULTILINE))


def _period_maxima(out: str) -> dict[str, float]:
    """First-group 1ST HIGHEST value of each MAXIMUM PERIOD summary, by column heading."""
    maxima = {}
    for block in out.split("THE SUMMARY OF MAXIMUM PERIOD")[1:]:
        label = re.search(r"^GROUP ID\s+(.+?)\s+RECEPTOR", block, flags=re.MULTILINE).group(1)
        value = re.search(r"1ST HIGHEST VALUE IS\s+(\S+)", block).group(1)
        maxima[label] = float(value)
    return maxima


def test_period_maxima_reads_each_summary():
    out = (
        "*** THE SUMMARY OF MAXIMUM PERIOD (    96 HRS) RESULTS ***\n"
        "GROUP ID                           DRY DEPO                RECEPTOR  (XR, YR)\n"
        "ALL       1ST HIGHEST VALUE IS       0.02393 AT (    -100.00,      500.00)\n"
        "*** THE SUMMARY OF MAXIMUM PERIOD (    96 HRS) RESULTS ***\n"
        "GROUP ID                           WET DEPO                RECEPTOR  (XR, YR)\n"
        "ALL       1ST HIGHEST VALUE IS       0.04199 AT (       0.00,     -100.00)\n"
    )
    assert _period_maxima(out) == {"DRY DEPO": 0.02393, "WET DEPO": 0.04199}


@pytest.mark.skipif(shutil.which("aermod") is None, reason="AERMOD binary not found on PATH")
@pytest.mark.parametrize("deck_name", sorted(DECKS))
def test_deck_runs_with_real_aermod(decks, tmp_path, deck_name):
    # Four days of EPA's Houston met with 28.4 mm of rain, so wet
    # deposition and wet depletion have something to act on. An ANNUAL
    # average on less than a year of met is E480, so this run asks for
    # PERIOD instead; everything else is the example's deck as written.
    shutil.copy(MET / f"{MET_STEM}.SFC", tmp_path / "met_2023.sfc")
    shutil.copy(MET / f"{MET_STEM}.PFL", tmp_path / "met_2023.pfl")
    deck = (decks / deck_name).read_text()
    (avertime,) = _cards(deck, "AVERTIME")
    assert "ANNUAL" in avertime
    deck = deck.replace("AVERTIME  ANNUAL", "AVERTIME  PERIOD")
    (modelopt,) = _cards(deck, "MODELOPT")
    inp = tmp_path / deck_name
    inp.write_text(deck)

    result = AERMODRunner().run(str(inp), working_dir=str(tmp_path), timeout=600)

    out = Path(result.output_file).read_text(encoding="latin-1")
    assert result.success, result.error_message
    assert _warnings(out) <= ALLOWED_WARNINGS, sorted(_warnings(out) - ALLOWED_WARNINGS)
    assert "Overrides" not in out  # e.g. W206: DFAULT overriding FLAT
    assert "IN GRAMS/M**2" in out
    maxima = _period_maxima(out)
    for quantity in ("CONC", "DEPOS", "DDEP", "WDEP"):
        label = QUANTITY_LABEL[quantity]
        if quantity in modelopt:
            assert maxima.get(label, 0.0) > 0.0, (label, maxima)
        else:
            assert label not in maxima, (label, maxima)

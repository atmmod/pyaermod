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
(skipped when ``aermod`` is not on PATH) and checks that it finishes
and writes deposition tables in g/m**2.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from pyaermod import AERMODRunner

REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples" / "deposition_modeling.py"
FIXT = REPO / "tests" / "fixtures" / "epa_official"

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
        {"CONC", "DEPOS", "DDEP", "WDEP", "DFAULT"},
        set(),
    ),
    "multi_source_deposition.inp": (
        "example_3_multi_source_groups",
        {"CONC", "DDEP", "ALPHA"},
        {"DFAULT"},
    ),
}
GAS_DECKS = ("gas_deposition.inp", "multi_source_deposition.inp")


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
    assert sources == with_inputs


def test_example_does_not_rely_on_output_type():
    # output_type selects nothing in AERMOD; the example must not set it.
    assert "output_type=" not in EXAMPLE.read_text()


def test_example_states_deposition_units():
    text = EXAMPLE.read_text()
    assert "g/m2/s" not in text
    assert "g/m**2/yr" in text


@pytest.mark.skipif(shutil.which("aermod") is None, reason="AERMOD binary not found on PATH")
@pytest.mark.parametrize("deck_name", sorted(DECKS))
def test_deck_runs_with_real_aermod(decks, tmp_path, deck_name):
    # The vendored met is four days of 1988 (AERMET2), and an ANNUAL
    # average on less than a year of met is E480, so this run asks for
    # PERIOD instead; everything else is the example's deck as written.
    shutil.copy(FIXT / "AERMET2.SFC", tmp_path / "met_2023.sfc")
    shutil.copy(FIXT / "AERMET2.PFL", tmp_path / "met_2023.pfl")
    deck = (decks / deck_name).read_text()
    (avertime,) = _cards(deck, "AVERTIME")
    assert "ANNUAL" in avertime
    deck = deck.replace("AVERTIME  ANNUAL", "AVERTIME  PERIOD")
    inp = tmp_path / deck_name
    inp.write_text(deck)

    result = AERMODRunner().run(str(inp), working_dir=str(tmp_path), timeout=600)

    out = " ".join(Path(result.output_file).read_text(encoding="latin-1").split())
    assert result.success, result.error_message
    assert "DRY DEPOSITION VALUES" in out
    assert "IN GRAMS/M**2" in out
    if deck_name == "particle_deposition.inp":
        assert "TOTAL DEPOSITION VALUES" in out
        assert "WET DEPOSITION VALUES" in out

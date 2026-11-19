"""Deck-reader behaviour checked against AERMOD v24142 / v26135.

Every deck here (except the malformed-line ones, which AERMOD rejects)
runs through AERMOD's setup without an error; the reader must read it
and the writer must give it back with the same meaning.
"""

from __future__ import annotations

import pytest

from pyaermod.input_reader import parse_aermod_input

_DECK = """\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC FLAT
   AVERTIME  1 24 PERIOD
   POLLUTID  OTHER
{co}   RUNORNOT  RUN
CO FINISHED
SO STARTING
   LOCATION  S1 POINT {x} 0 0
   SRCPARAM  S1 1.0 30 400 10 1
{so}   SRCGROUP  ALL
{groups}SO FINISHED
RE STARTING
   DISCCART  500 0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  14735 1988
   UAIRDATA  14735 1988
   PROFBASE  0 METERS
ME FINISHED
OU STARTING
{ou}OU FINISHED
"""


def _deck(co="", so="", groups="", ou="   RECTABLE  ALLAVE FIRST\n", x="0"):
    return _DECK.format(co=co, so=so, groups=groups, ou=ou, x=x)


def _cards(text, keyword):
    return [ln.split()[1:] for ln in text.splitlines() if ln.split()[:1] == [keyword]]


# ---------------------------------------------------------------------
# B1: AERMOD reads numbers with STODBL, which takes a Fortran D exponent.
# ---------------------------------------------------------------------

def test_location_with_d_exponent():
    p = parse_aermod_input(_deck(x="1.0D2"))
    assert p.sources.sources[0].x_coord == pytest.approx(100.0)


def test_halflife_with_d_exponent():
    p = parse_aermod_input(_deck(co="   HALFLIFE  1.0D3\n"))
    assert p.control.half_life == pytest.approx(1000.0)


def test_urbanopt_with_d_exponent_is_kept():
    p = parse_aermod_input(_deck(co="   URBANOPT  1.0D6\n", so="   URBANSRC  S1\n"))
    text = p.to_aermod_input(validate=False)
    assert _cards(text, "URBANOPT"), "the urban area was dropped"


def test_bare_halflife_is_a_value_error():
    """EDECAY E200 in AERMOD; the reader's contract is ValueError."""
    with pytest.raises(ValueError):
        parse_aermod_input(_deck(co="   HALFLIFE\n"))


# ---------------------------------------------------------------------
# B2: "Nothing is dropped silently" (input_reader module docstring).
# ---------------------------------------------------------------------

@pytest.mark.parametrize("card", [
    "PARTDIAM  S1 abc",
    "BUILDHGT  S1 x y",
    "NO2RATIO  S1 abc",
    "GASDEPOS  S1 1 2",
])
def test_malformed_so_card_is_kept(card):
    p = parse_aermod_input(_deck(so=f"   {card}\n"))
    kept = [ln.keyword for ln in p.unparsed_lines]
    assert card.split()[0] in kept


# ---------------------------------------------------------------------
# B3: AERMOD upper-cases the whole image (setup.f LWRUPR) before it
# splits it; only file names, titles and a few labels are read from the
# original-case RUNST1.
# ---------------------------------------------------------------------

def test_lower_case_pathway_codes():
    deck = "\n".join(ln[:2].lower() + ln[2:] for ln in _deck().splitlines()) + "\n"
    p = parse_aermod_input(deck)
    assert [s.source_id.upper() for s in p.sources.sources] == ["S1"]


def test_source_id_case_does_not_split_a_source():
    deck = _deck().replace("LOCATION  S1", "LOCATION  Stack9").replace("SRCPARAM  S1", "SRCPARAM  STACK9")
    p = parse_aermod_input(deck)
    assert [s.source_id.upper() for s in p.sources.sources] == ["STACK9"]
    assert not p.unparsed_lines


def test_group_member_case_matches_source():
    p = parse_aermod_input(_deck(groups="   SRCGROUP  G1 s1\n"))
    text = p.to_aermod_input()  # validates: the member must resolve
    assert [m.upper() for m in _cards(text, "SRCGROUP")[-1][1:]] == ["S1"]


def test_file_names_keep_their_case():
    deck = _deck().replace("SURFFILE  a.sfc", "SURFFILE  My.SFC")
    p = parse_aermod_input(deck)
    assert p.meteorology.surface_file == "My.SFC"


# ---------------------------------------------------------------------
# B6: RECTABLE / MAXTABLE / DAYTABLE are per averaging period (ouset.f
# OUTQA / RECTAB / MAXTAB / DAYTAB). Collapsing them to ALLAVE adds
# tables AERMOD then prints (verified: 2ND/3RD 24-HR tables, a MAXIMUM 5
# 1-HR table, 96 hourly DAYTABLE pages).
# ---------------------------------------------------------------------

_RANKS = {"FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6}


def _rectable(text):
    """{period: set of ranks} requested by the RECTABLE cards."""
    want = {}
    for card in _cards(text, "RECTABLE"):
        period, ranks = card[0], set()
        for tok in card[1:]:
            if "-" in tok:
                lo, hi = tok.split("-")
                ranks |= set(range(int(lo), int(hi) + 1))
            else:
                ranks.add(_RANKS.get(tok) or int(tok))
        periods = ["1", "24", "PERIOD"] if period == "ALLAVE" else [period]
        for per in periods:
            want.setdefault(per, set()).update(ranks)
    return want


def test_rectable_per_period_survives_rewrite():
    deck = _deck(ou="   RECTABLE  1 1-3\n   RECTABLE  24 1\n")
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert _rectable(text) == _rectable(deck)


def test_maxtable_period_survives_rewrite():
    deck = _deck(ou="   RECTABLE  ALLAVE FIRST\n   MAXTABLE  24 5\n")
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert _cards(text, "MAXTABLE") == [["24", "5"]]


def test_daytable_period_survives_rewrite():
    deck = _deck(ou="   RECTABLE  ALLAVE FIRST\n   DAYTABLE  24\n")
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert _cards(text, "DAYTABLE") == [["24"]]


# ---------------------------------------------------------------------
# Smaller reader fixes from the same review (slice-b B7-B10, arch A2).
# ---------------------------------------------------------------------

def test_low_wind_keeps_every_field():
    """coset.f LOW_WND reads up to seven fields (SVMIN WSMIN FRANMAX ...)."""
    deck = _deck(co="   LOW_WIND  0.3 0.5 0.95\n").replace("CONC FLAT", "CONC FLAT ALPHA")
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert _cards(text, "LOW_WIND") == [["0.3", "0.5", "0.95"]]


def test_latin1_and_bom_decks_are_read(tmp_path):
    from pyaermod.input_reader import read_aermod_input

    latin = tmp_path / "latin.inp"
    latin.write_bytes(_deck().replace("TITLEONE  t", "TITLEONE  Caf\xe9").encode("latin-1"))
    assert read_aermod_input(latin).control.title_one == "Caf\xe9"
    bom = tmp_path / "bom.inp"
    bom.write_bytes(b"\xef\xbb\xbf" + _deck().encode())
    assert [s.source_id for s in read_aermod_input(bom).sources.sources] == ["S1"]


def test_station_cards_keep_their_year_name_and_coordinates():
    deck = _deck().replace("SURFDATA  14735 1988", "SURFDATA  14735 1988 ALBANY 42.7 -73.8") \
                  .replace("UAIRDATA  14735 1988", "UAIRDATA  14735 1987")
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert _cards(text, "SURFDATA") == [["14735", "1988", "ALBANY", "42.7", "-73.8"]]
    assert _cards(text, "UAIRDATA") == [["14735", "1987"]]


def test_one_field_surfdata_is_a_value_error():
    """meset.f SFDATA: E201; the reader used to add its own SURFDATA beside it."""
    with pytest.raises(ValueError, match="SURFDATA"):
        parse_aermod_input(_deck().replace("SURFDATA  14735 1988", "SURFDATA  14735"))


def test_incomplete_grid_is_kept_verbatim_not_invented():
    """reset.f: a network without points is E221; no default 10 x 10 grid."""
    deck = _deck().replace("   DISCCART  500 0\n",
                           "   DISCCART  500 0\n   GRIDCART  C1 STA\n   GRIDCART  C1 END\n")
    p = parse_aermod_input(deck)
    assert p.receptors.cartesian_grids == []
    assert [u.keyword for u in p.unparsed_lines] == ["GRIDCART", "GRIDCART"]


def test_file_names_with_blanks_are_stored_bare_and_written_quoted():
    deck = _deck(ou='   RECTABLE  ALLAVE FIRST\n   SUMMFILE  "my out.sum"\n'
                    '   POSTFILE  1 ALL PLOT "my post.pst"\n')
    p = parse_aermod_input(deck)
    assert p.output.summary_file == "my out.sum"
    assert p.output.postfile == "my post.pst"
    text = p.to_aermod_input(validate=False)
    assert 'SUMMFILE  "my out.sum"' in text
    assert '"my post.pst"' in text
    assert parse_aermod_input(text).output.postfile == "my post.pst"


@pytest.mark.parametrize("card", [
    "MASSFRAX  S1 x",
    "PARTDENS  S1 x",
    "AREAVERT  S1 x 1",
    "EMISUNIT  abc g/s ug",
    "RBARRIER  S1 x 1",
    "URBANSRC",
])
def test_more_malformed_so_cards_are_kept(card):
    p = parse_aermod_input(_deck(so=f"   {card}\n"))
    assert card.split()[0] in [ln.keyword for ln in p.unparsed_lines]


@pytest.mark.parametrize("card", ["NO2STACK  abc", "O3SECTOR  1 x", "GASDEPVD  x",
                                  "URBANOPT  abc", "LOW_WIND"])
def test_malformed_co_cards_are_kept(card):
    p = parse_aermod_input(_deck(co=f"   {card}\n"))
    assert card.split()[0] in [ln.keyword for ln in p.unparsed_lines]


def test_maxtable_with_bad_rank_is_kept():
    p = parse_aermod_input(_deck(ou="   RECTABLE  ALLAVE FIRST\n   MAXTABLE  ALLAVE x\n"))
    assert "MAXTABLE" in [ln.keyword for ln in p.unparsed_lines]


def test_numbers_with_d_exponents_elsewhere():
    p = parse_aermod_input(_deck(co="   FLAGPOLE  1.5D0\n").replace(
        "   PROFBASE  0 METERS\n", "   PROFBASE  0 METERS\n   WDROTATE  1.0D1\n"))
    assert p.control.flag_pole_height == pytest.approx(1.5)
    assert p.meteorology.wind_rotation == pytest.approx(10.0)


def test_multi_urban_deck_round_trips():
    """soset.f URBANS with several URBANOPT cards: ``URBANSRC urbid srcid``."""
    deck = _deck(co="   URBANOPT  A1 500000\n   URBANOPT  B2 200000\n",
                 so="   LOCATION  S2 POINT 10 0 0\n   SRCPARAM  S2 1.0 30 400 10 1\n"
                    "   URBANSRC  A1 S1\n   URBANSRC  B2 S2\n")
    text = parse_aermod_input(deck).to_aermod_input(validate=False)
    assert sorted(_cards(text, "URBANSRC")) == [["A1", "S1"], ["B2", "S2"]]

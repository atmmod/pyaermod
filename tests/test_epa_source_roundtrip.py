"""EPA's own decks round-trip the source-construction keywords of reader
tranche 2 without losing a field.

Companion to :mod:`tests.test_epa_deck_roundtrip` (which covers the CO
and OU keywords of tranche 1) for the SO keywords: AREAVERT, BLPINPUT,
BLPGROUP, OLMGROUP, PSDGROUP, NO2RATIO, EMISUNIT, CONCUNIT, DEPOUNIT,
RBARRIER, RDEPRESS, SBARRIER, VBARRIER, RLEMCONV, GASDEPOS and URBANSRC,
plus the LOCATION and SRCPARAM lines of the source types the tranche
constructs (AREAPOLY, BUOYLINE, RLINEXT, LINE). Two tiers as before: the
vendored decks under ``tests/fixtures/epa_official`` run everywhere, the
whole archive runs when ``find_epa_testcase_set`` finds one.

"Round-trips" means: parse, write, parse again, and (a) the source
objects of the tranche's types compare equal and (b) the multiset of the
keyword lines above matches token for token, numbers compared as
numbers (``3.6D6`` and ``3.6e+06`` agree), labels case-insensitively
(AERMOD upper-cases every field it reads).

Two AERMOD behaviours mean a line may legitimately come back reshaped:
the eight-field BLPINPUT with no BLPGROUP is the implicit group "ALL",
which the writer keeps as such; and SRCGROUP / BLPGROUP / OLMGROUP
continuation lines are merged (soset.f files a non-adjacent
continuation under the last group defined, so the writer never
separates them). Neither appears in EPA's decks except where the
comparison below allows it.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from pyaermod.input_generator import (
    AreaPolySource,
    BuoyLineSource,
    LineSource,
    PointCapSource,
    PointHorSource,
    RLineExtSource,
    SidewashPointSource,
)
from pyaermod.input_reader import parse_aermod_input

from .test_epa_deck_roundtrip import archive_inputs_dir

FIXTURES = Path(__file__).parent / "fixtures" / "epa_official"
ROOT = Path(__file__).resolve().parent.parent

KEYWORDS = (
    "AREAVERT", "BLPINPUT", "BLPGROUP", "OLMGROUP", "PSDGROUP", "NO2RATIO",
    "EMISUNIT", "CONCUNIT", "DEPOUNIT", "RBARRIER", "RDEPRESS", "SBARRIER",
    "VBARRIER", "RLEMCONV", "GASDEPOS", "URBANSRC",
    "METHOD_2", "PLATFORM", "ARCFTSRC", "HBPSRCID",
)
CONSTRUCTED_TYPES = ("AREAPOLY", "BUOYLINE", "RLINEXT", "LINE", "POINTCAP", "POINTHOR", "SWPOINT")

_LINE_RE = re.compile(
    r"^\s*(?:SO\s+)?(" + "|".join((*KEYWORDS, "LOCATION", "SRCPARAM")) + r")\b(.*)$",
    re.IGNORECASE,
)


def _norm(tok: str) -> str:
    try:
        return repr(float(tok))
    except ValueError:
        try:
            return repr(float(tok.replace("D", "e").replace("d", "e")))
        except ValueError:
            return tok.upper()


def keyword_lines(text: str) -> Counter:
    """Normalised (keyword, fields) tuples for the tranche's lines.

    LOCATION and SRCPARAM lines count only for the constructed source
    types; the ID on a SRCPARAM line is matched against the LOCATION
    lines of the same text.
    """
    typed: dict = {}
    parsed = []
    for line in text.splitlines():
        if line.lstrip().startswith("**"):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        keyword, toks = m.group(1).upper(), m.group(2).split()
        if keyword == "LOCATION" and len(toks) > 1:
            typed[toks[0]] = toks[1].upper()
        parsed.append((keyword, toks))
    out: Counter = Counter()
    for keyword, toks in parsed:
        if (keyword in ("LOCATION", "SRCPARAM")
                and typed.get(toks[0] if toks else "") not in CONSTRUCTED_TYPES):
            continue
        out[(keyword, tuple(_norm(t) for t in toks))] += 1
    return out


def _merge_areavert(lines: Counter) -> Counter:
    """AREAVERT pairs may be wrapped differently (EPA writes five pairs to
    a line, pyaermod six; ARVERT accumulates either way): compare the
    ring per source with the pairs concatenated in order."""
    merged: Counter = Counter()
    rings: dict = {}
    for (keyword, toks), n in lines.items():
        if keyword == "AREAVERT" and toks:
            rings.setdefault(toks[0], []).append((n, toks[1:]))
        else:
            merged[(keyword, toks)] += n
    for sid, chunks in rings.items():
        values: list = []
        for n, toks in chunks:
            values.extend(toks * n)
        merged[("AREAVERT", (sid, *values))] += 1
    return merged


def _constructed_sources(project):
    return [s for s in project.sources.sources
            if isinstance(s, (AreaPolySource, BuoyLineSource, RLineExtSource, LineSource,
                              PointCapSource, PointHorSource, SidewashPointSource))]


def assert_roundtrip(path: Path) -> int:
    text = path.read_text(encoding="latin-1")
    first = parse_aermod_input(text)
    written = first.to_aermod_input(validate=False)
    second = parse_aermod_input(written)
    assert _constructed_sources(second) == _constructed_sources(first), path.name
    assert second.sources.psd_groups == first.sources.psd_groups
    assert second.sources.solid_barriers == first.sources.solid_barriers
    # METHOD_2 travels on the source it names (a range resolves to IDs).
    assert [(s.source_id, getattr(s, "method_2", None)) for s in second.sources.sources] == \
        [(s.source_id, getattr(s, "method_2", None)) for s in first.sources.sources]
    for attr in ("emission_units", "concentration_units", "deposition_units",
                 "rline_moves_units", "aircraft_sources", "hbp_sources"):
        assert getattr(second.sources, attr) == getattr(first.sources, attr), attr
    if first.control.chemistry is not None:
        assert second.control.chemistry.olm_groups == first.control.chemistry.olm_groups
    before = _merge_areavert(keyword_lines(text))
    after = _merge_areavert(keyword_lines(written))
    assert after == before, (
        f"{path.name}: keyword lines changed\n  lost: {before - after}\n  gained: {after - before}"
    )
    return sum(before.values())


VENDORED = sorted(FIXTURES.glob("*.inp"))


@pytest.mark.parametrize("path", VENDORED, ids=[p.name for p in VENDORED])
def test_vendored_epa_deck_roundtrips(path):
    assert_roundtrip(path)


def test_vendored_decks_cover_every_keyword_epa_uses():
    """The vendored subset carries every tranche-2 keyword the archive uses."""
    seen = set()
    for path in VENDORED:
        seen |= {k for k, _ in keyword_lines(path.read_text(encoding="latin-1"))}
    # EPA's 53 decks use no NO2RATIO, EMISUNIT (commented out), CONCUNIT,
    # SBARRIER, VBARRIER or RLEMCONV; those forms are covered by
    # tests/test_so_source_construction.py and the acceptance tests.
    assert {"AREAVERT", "BLPINPUT", "BLPGROUP", "OLMGROUP", "PSDGROUP", "DEPOUNIT",
            "RBARRIER", "RDEPRESS", "GASDEPOS", "URBANSRC", "LOCATION", "SRCPARAM",
            "METHOD_2"} <= seen, sorted(seen)


def test_the_comparison_can_fail():
    """A dropped AREAVERT pair must be reported, or the checks prove nothing."""
    text = (FIXTURES / "allsrcs.inp").read_text(encoding="latin-1")
    broken = text.replace("-10.0 20.0  -10.0 10.0  -10.0 0.0", "-10.0 20.0  -10.0 10.0")
    assert broken != text
    assert _merge_areavert(keyword_lines(broken)) != _merge_areavert(keyword_lines(text))


# An inputs-only unpack is enough, as for the tranche-1 round-trip test.
_ARCHIVE_INPUTS = archive_inputs_dir(ROOT / "test_cases")
_ARCHIVE_DECKS = sorted(_ARCHIVE_INPUTS.glob("*.inp")) if _ARCHIVE_INPUTS else []


@pytest.mark.skipif(not _ARCHIVE_DECKS, reason="EPA test-case archive not unpacked under test_cases/")
@pytest.mark.parametrize("path", _ARCHIVE_DECKS, ids=[p.name for p in _ARCHIVE_DECKS])
def test_archive_epa_deck_roundtrips(path):
    assert_roundtrip(path)

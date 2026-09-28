"""EPA's own decks round-trip through the reader and writer without losing
anything: the keywords pyaermod models structurally come back equal, and
every other line is accounted for in ``AERMODProject.unparsed_lines``.

Two tiers. The vendored decks under ``tests/fixtures/epa_official`` run
everywhere; the whole v26135 archive (53 decks) runs when
``find_epa_testcase_set`` finds a set under ``test_cases/`` or
``$PYAERMOD_EPA_TESTCASES`` (the ``epa_parity.yml`` workflow unpacks one).

"Round-trips" means: parse the deck, write it back with pyaermod, parse
that, and compare

(a) the CO, RE, ME and OU pathways field for field, the SO group
    definitions and source IDs, and the preserved lines (pathway,
    keyword, fields) -- so nothing the model holds can be silently
    dropped or renormalised;
(b) the multiset of the keyword lines in :data:`STRUCTURAL_KEYWORDS`,
    token for token after case and whitespace normalisation, so a value
    or a trailing optional field cannot be lost on the way out;
(c) that every line of the original deck is either a keyword the reader
    models (:data:`MODELLED_KEYWORDS`, the list the reader's docstring
    claims) or present in ``unparsed_lines`` -- the accounting the
    docstring promises.

Whether AERMOD accepts what the writer produced is a separate question,
answered with the binary in ``tests/test_epa_deck_acceptance.py``.
"""

from __future__ import annotations

import dataclasses
import re
from collections import Counter
from pathlib import Path

import pytest

from pyaermod.epa_testcases import (
    ENV_VAR,
    find_epa_testcase_set,
    list_epa_testcase_sets,
)
from pyaermod.input_reader import _group_keywords, _split_pathways, parse_aermod_input
from pyaermod.versions import VALIDATED_AERMOD_VERSIONS

FIXTURES = Path(__file__).parent / "fixtures" / "epa_official"
ROOT = Path(__file__).resolve().parent.parent

#: Keywords whose lines are compared token for token. Value tokens are
#: compared numerically so ``40.`` and ``40`` agree; filenames keep case.
STRUCTURAL_KEYWORDS = (
    "MULTYEAR", "SAVEFILE", "INITFILE",
    "NOXVALUE", "NOX_FILE", "NOX_VALS", "NOX_UNIT", "NOXSECTR",
    "O3SECTOR", "OZONUNIT", "OZONEVAL", "OZONEFIL", "O3VALUES",
    "MAXDAILY", "MXDYBYYR", "MAXDCONT", "FILEFORM", "MAXIFILE",
    "GASDEPDF", "GASDEPVD", "GDSEASON", "GDLANUSE",
    "URBANOPT", "STARTEND",
    "EVENTPER", "EVENTLOC", "EVENTOUT", "EVENTFIL",
    "DAYRANGE", "NUMYEARS", "WINDCATS", "SCIMBYHR", "NOTURB", "NOTURBST", "NOTURBCO",
    "NOSA", "NOSW", "NOSAST", "NOSWST", "NOSACO", "NOSWCO",
    "NOHEADER", "RANKFILE", "SEASONHR", "EVALFILE", "TOXXFILE",
    "ARMRATIO", "AWMADWNW", "ORD_DWNW", "ARCFTOPT",
)

#: What the reader stores structurally, per pathway (its module docstring).
#: A deck line whose keyword is here is covered by (a); any other line
#: must be in unparsed_lines. SRCGROUP is listed because bare ``SRCGROUP
#: ALL`` is consumed into ``SourcePathway.include_all_group``.
MODELLED_KEYWORDS = {
    "CO": {"TITLEONE", "TITLETWO", "MODELOPT", "AVERTIME", "POLLUTID", "RUNORNOT",
           "ELEVUNIT", "FLAGPOLE", "URBANOPT", "LOW_WIND", "HALFLIFE", "DCAYCOEF",
           "NO2STACK", "OZONEVAL", "OZONEFIL", "O3VALUES", "O3SECTOR", "OZONUNIT",
           "NOXVALUE", "NOX_FILE", "NOX_VALS", "NOX_UNIT", "NOXSECTR", "GASDEPDF",
           "GASDEPVD", "GDSEASON", "GDLANUSE", "SAVEFILE", "INITFILE", "MULTYEAR",
           "EVENTFIL", "ARMRATIO", "AWMADWNW", "ORD_DWNW", "ARCFTOPT"},
    "SO": {"LOCATION", "SRCPARAM", "SRCGROUP", "BACKGRND", "BGSECTOR", "GASDEPOS",
           "PARTDIAM", "MASSFRAX", "PARTDENS", "URBANSRC", "BUILDHGT", "BUILDWID",
           "BUILDLEN", "XBADJ", "YBADJ", "AREAVERT", "BLPINPUT", "BLPGROUP",
           "OLMGROUP", "PSDGROUP", "NO2RATIO", "EMISUNIT", "CONCUNIT", "DEPOUNIT",
           "RLEMCONV", "RBARRIER", "RDEPRESS", "SBARRIER", "VBARRIER",
           "METHOD_2", "PLATFORM", "ARCFTSRC", "HBPSRCID"},
    "RE": {"GRIDCART", "GRIDPOLR", "DISCCART", "ELEVUNIT"},
    "ME": {"SURFFILE", "PROFFILE", "SURFDATA", "UAIRDATA", "PROFBASE", "STARTEND",
           "WDROTATE", "DAYRANGE", "NUMYEARS", "WINDCATS", "SCIMBYHR", "NOTURB",
           "NOTURBST", "NOTURBCO", "NOSA", "NOSW", "NOSAST", "NOSWST", "NOSACO", "NOSWCO"},
    "OU": {"RECTABLE", "MAXTABLE", "DAYTABLE", "SUMMFILE", "MAXIFILE", "PLOTFILE",
           "POSTFILE", "FILEFORM", "MAXDAILY", "MXDYBYYR", "MAXDCONT", "EVENTOUT",
           "NOHEADER", "RANKFILE", "SEASONHR", "EVALFILE", "TOXXFILE"},
    "EV": {"EVENTPER", "EVENTLOC"},
}

_LINE_RE = re.compile(
    r"^\s*(?:CO|OU|ME|EV)?\s*(" + "|".join(STRUCTURAL_KEYWORDS) + r")\b(.*)$", re.IGNORECASE,
)
_REPEAT_RE = re.compile(r"^(\d+)\*(.+)$")


def _norm_token(tok: str) -> str:
    try:
        return repr(float(tok))
    except ValueError:
        return tok


def keyword_lines(text: str) -> Counter:
    """Normalised (keyword, fields) tuples for the structural keywords."""
    out: Counter = Counter()
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        keyword = m.group(1).upper()
        toks: list[str] = []
        for tok in m.group(2).split():
            rep = _REPEAT_RE.match(tok)
            if rep:
                toks.extend([_norm_token(rep.group(2))] * int(rep.group(1)))
            else:
                toks.append(_norm_token(tok))
        # Units and flags are case-insensitive in AERMOD (FIELD is
        # upper-cased); filenames and formats are not, and stay as is.
        if keyword in ("OZONEVAL", "NOXVALUE", "OZONUNIT", "NOX_UNIT", "FILEFORM",
                       "O3VALUES", "NOX_VALS", "MAXIFILE", "EVENTOUT", "EVENTLOC",
                       "NOHEADER", "WINDCATS", "DAYRANGE", "AWMADWNW", "ORD_DWNW"):
            toks = [t.upper() if i != 3 else t for i, t in enumerate(toks)] \
                if keyword == "MAXIFILE" else [t.upper() for t in toks]
        elif keyword in ("OZONEFIL", "NOX_FILE"):
            toks = [t.upper() if i == 1 else t for i, t in enumerate(toks)]
            if toks and toks[0].upper().startswith("SECT"):
                toks = [toks[0].upper()] + toks[1:2] + [t.upper() for t in toks[2:3]] + toks[3:]
        out[(keyword, tuple(toks))] += 1
    return out


def _merge_continuations(lines: Counter) -> Counter:
    """O3VALUES / NOX_VALS values may be split over several lines on
    either side; compare per flag with the values concatenated."""
    merged: Counter = Counter()
    profiles: dict = {}
    for (keyword, toks), n in lines.items():
        if keyword in ("O3VALUES", "NOX_VALS") and n == 1:
            head = toks[:2] if toks and toks[0].startswith("SECT") else toks[:1]
            profiles.setdefault((keyword, head), []).extend(toks[len(head):])
        else:
            merged[(keyword, toks)] += n
    for (keyword, head), values in profiles.items():
        merged[(keyword, head + tuple(sorted(values)))] += 1
    return merged


def _wp1_fields(project):
    c, o, chem = project.control, project.output, project.control.chemistry
    return {
        "multiyear": c.multiyear, "save_file": c.save_file, "init_file": c.init_file,
        "ozone": chem.ozone_data if chem else None,
        "nox": chem.nox_background if chem else None,
        "gas": (c.gas_deposition_defaults, c.gas_deposition_velocity,
                c.gas_deposition_seasons, c.gas_deposition_land_use),
        "file_format": o.file_format, "max_daily": o.max_daily_files,
        "by_year": o.max_daily_by_year_files, "contributions": o.max_daily_contributions,
    }


def _unparsed_keys(project):
    return sorted((u.pathway, u.keyword, tuple(u.fields)) for u in project.unparsed_lines)


def structural_differences(first, second) -> list[str]:
    """Field-level differences between two parses of the same deck."""
    diffs = []
    for pathway in ("control", "receptors", "meteorology", "output"):
        a, b = getattr(first, pathway), getattr(second, pathway)
        for f in dataclasses.fields(a):
            if getattr(a, f.name) != getattr(b, f.name):
                diffs.append(f"{pathway}.{f.name}: {getattr(a, f.name)!r} -> {getattr(b, f.name)!r}")
    # The writer puts SRCGROUP ALL first and joins continuation lines
    # (soset.f SOGRP semantics); membership per group is what must hold.
    groups = lambda p: sorted(  # noqa: E731
        (g.group_name, tuple(g.member_source_ids)) for g in p.sources.group_definitions)
    if groups(first) != groups(second):
        diffs.append(f"sources.group_definitions {groups(first)} -> {groups(second)}")
    if first.sources.include_all_group != second.sources.include_all_group:
        diffs.append("sources.include_all_group")
    ids = lambda p: [s.source_id for s in p.sources.sources]  # noqa: E731
    if ids(first) != ids(second):
        diffs.append(f"source ids {ids(first)} -> {ids(second)}")
    if first.events != second.events:
        diffs.append(f"events: {first.events!r} -> {second.events!r}")
    if first.event_processing != second.event_processing:
        diffs.append("event_processing")
    if _unparsed_keys(first) != _unparsed_keys(second):
        lost = set(_unparsed_keys(first)) - set(_unparsed_keys(second))
        gained = set(_unparsed_keys(second)) - set(_unparsed_keys(first))
        diffs.append(f"unparsed_lines lost {sorted(lost)} gained {sorted(gained)}")
    return diffs


def unaccounted_lines(text: str, project) -> list[str]:
    """Deck lines that are neither modelled nor kept in unparsed_lines."""
    kept = {u.lineno for u in project.unparsed_lines}
    out = []
    for code, block in _split_pathways(text).items():
        for keyword, _toks, lineno in _group_keywords(block):
            if lineno in kept or keyword in MODELLED_KEYWORDS.get(code, set()):
                continue
            out.append(f"{code} line {lineno}: {block.record(lineno).raw.strip()}")
    return out


def assert_roundtrip(path: Path) -> int:
    text = path.read_text(encoding="latin-1")
    first = parse_aermod_input(text)
    written = first.to_aermod_input(validate=False)
    second = parse_aermod_input(written)
    assert _wp1_fields(second) == _wp1_fields(first), path.name
    assert structural_differences(first, second) == [], path.name
    before = _merge_continuations(keyword_lines(text))
    after = _merge_continuations(keyword_lines(written))
    assert after == before, (
        f"{path.name}: keyword lines changed\n  lost: {before - after}\n  gained: {after - before}"
    )
    assert unaccounted_lines(text, first) == [], path.name
    # The preserved lines are written back exactly once, in their pathway.
    for line in first.unparsed_lines:
        segment = written[written.index(f"{line.pathway} STARTING"):
                          written.index(f"{line.pathway} FINISHED")]
        assert segment.count(line.to_aermod_line()) >= 1, (path.name, line.raw)
    return sum(before.values())


VENDORED = sorted(FIXTURES.glob("*.inp"))


@pytest.mark.parametrize("path", VENDORED, ids=[p.name for p in VENDORED])
def test_vendored_epa_deck_roundtrips(path):
    assert_roundtrip(path)


def test_vendored_decks_cover_every_keyword_epa_uses():
    """The vendored subset carries every keyword form the archive does
    for the keywords this suite compares token for token, and the runstream
    forms the RE and OU parsers were rewritten for."""
    seen = set()
    forms = set()
    for path in VENDORED:
        text = path.read_text(encoding="latin-1")
        seen |= {k for k, _ in keyword_lines(text)}
        for block in _split_pathways(text).values():
            for rec in block.records:
                if rec.continuation:
                    forms.add("continuation")
                sub = [t.upper() for t in rec.fields[:2]]
                if rec.keyword == "GRIDPOLR" and "GDIR" in sub:
                    forms.add("GDIR")
                if rec.keyword == "GRIDPOLR" and "DIST" in sub:
                    forms.add("DIST")
                if rec.keyword == "GRIDCART" and ("XPNTS" in sub or "YPNTS" in sub):
                    forms.add("XPNTS")
                if rec.keyword == "URBANOPT":
                    forms.add("URBANOPT")
    assert {"MULTYEAR", "NOXVALUE", "OZONEVAL", "OZONEFIL", "MAXDCONT",
            "FILEFORM", "GDSEASON", "GDLANUSE", "MAXIFILE", "URBANOPT",
            "EVENTPER", "EVENTLOC", "EVENTOUT", "SEASONHR", "RANKFILE", "SCIMBYHR",
            "ARMRATIO"} <= seen, sorted(seen)
    assert {"continuation", "GDIR", "DIST", "XPNTS", "URBANOPT"} <= forms, sorted(forms)


def test_vendored_decks_exercise_the_unparsed_path():
    """The vendored decks keep at least these keyword lines verbatim, so the
    accounting in unaccounted_lines() is not passing vacuously."""
    kept = set()
    for path in VENDORED:
        project = parse_aermod_input(path.read_text(encoding="latin-1"))
        kept |= {(u.pathway, u.keyword) for u in project.unparsed_lines}
    expected = {("CO", "ERRORFIL"), ("SO", "EMISFACT"), ("SO", "INCLUDED"),
                ("RE", "INCLUDED"), ("RE", "DISCPOLR"), ("RE", "EVALCART"),
                ("ME", "SITEDATA"), ("OU", "POSTFILE")}
    assert expected <= kept, sorted(expected - kept)


def archive_inputs_dir(root: Path, env=None) -> Path | None:
    """The ``inputs/`` directory of an EPA reference set under ``root``.

    ``find_epa_testcase_set`` accepts a set only when its ``postfiles/``
    tree is present too, because the parity harness scores against
    those references. This check reads decks alone, so a set unpacked
    with just ``inputs/`` (what the keyword-oracle workflow and a
    developer checking the reader typically have) must count. The
    resolver's choice wins when it has one; otherwise the newest
    validated release with an ``inputs/`` directory, then the newest on
    disk. ``$PYAERMOD_EPA_TESTCASES`` is honoured either way.
    """
    full = find_epa_testcase_set(root, env=env)
    if full is not None:
        return full.inputs if full.inputs.is_dir() else None
    partial = [s for s in list_epa_testcase_sets(root) if s.inputs.is_dir()]
    if not partial:
        return None
    for validated in VALIDATED_AERMOD_VERSIONS:
        matching = [s for s in partial if s.aermod_version == validated]
        if matching:
            return matching[-1].inputs
    return max(partial, key=lambda s: (int(s.aermod_version or 0), s.name)).inputs


def test_archive_inputs_dir_accepts_an_inputs_only_unpack(tmp_path):
    """An inputs-only unpack is enough for this module; postfiles are not needed."""
    older = tmp_path / "aermet24142_aermod24142" / "inputs"
    newer = tmp_path / "aermet26135_aermod26135" / "inputs"
    for d in (older, newer):
        d.mkdir(parents=True)
        (d / "x.inp").write_text("")
    assert archive_inputs_dir(tmp_path, env={}) == newer
    # The override names a set directory, as everywhere else in pyaermod.
    assert archive_inputs_dir(tmp_path, env={ENV_VAR: str(older.parent)}) == older
    assert archive_inputs_dir(tmp_path / "missing", env={}) is None


_ARCHIVE_INPUTS = archive_inputs_dir(ROOT / "test_cases")
_ARCHIVE_DECKS = sorted(_ARCHIVE_INPUTS.glob("*.inp")) if _ARCHIVE_INPUTS else []


@pytest.mark.skipif(not _ARCHIVE_DECKS, reason="EPA test-case archive not unpacked under test_cases/")
@pytest.mark.parametrize("path", _ARCHIVE_DECKS, ids=[p.name for p in _ARCHIVE_DECKS])
def test_archive_epa_deck_roundtrips(path):
    assert_roundtrip(path)


@pytest.mark.skipif(not _ARCHIVE_DECKS, reason="EPA test-case archive not unpacked under test_cases/")
def test_archive_is_the_whole_v26135_set():
    """Guard against a partial unpack passing as the suite-wide check."""
    assert len(_ARCHIVE_DECKS) == 53, [p.name for p in _ARCHIVE_DECKS]

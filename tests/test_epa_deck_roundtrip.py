"""EPA's own decks round-trip through the reader and writer without losing
the keywords pyaermod models structurally.

Two tiers. The vendored decks under ``tests/fixtures/epa_official`` run
everywhere; the whole v26135 archive (53 decks) runs when
``find_epa_testcase_set`` finds a set under ``test_cases/`` or
``$PYAERMOD_EPA_TESTCASES`` (the ``epa_parity.yml`` workflow unpacks one).

"Round-trips" means: parse the deck, write it back with pyaermod, parse
that, and compare (a) every structural field for the keywords in
:data:`STRUCTURAL_KEYWORDS` and (b) the multiset of those keyword lines,
token for token after case and whitespace normalisation, so a value or a
trailing optional field cannot be silently dropped or reordered.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from pyaermod.epa_testcases import (
    ENV_VAR,
    find_epa_testcase_set,
    list_epa_testcase_sets,
)
from pyaermod.input_reader import parse_aermod_input
from pyaermod.versions import VALIDATED_AERMOD_VERSIONS

FIXTURES = Path(__file__).parent / "fixtures" / "epa_official"
ROOT = Path(__file__).resolve().parent.parent

#: Keywords whose lines are compared token for token. Value tokens are
#: compared numerically so ``40.`` and ``40`` agree; filenames keep case.
STRUCTURAL_KEYWORDS = (
    "MULTYEAR", "SAVEFILE", "INITFILE",
    "NOXVALUE", "NOX_FILE", "NOX_VALS", "NOX_UNIT", "NOXSECTR",
    "O3SECTOR", "OZONUNIT", "OZONEVAL", "OZONEFIL", "O3VALUES",
    "MAXDAILY", "MXDYBYYR", "MAXDCONT", "FILEFORM",
    "GASDEPDF", "GASDEPVD", "GDSEASON", "GDLANUSE",
)

_LINE_RE = re.compile(
    r"^\s*(?:CO|OU)?\s*(" + "|".join(STRUCTURAL_KEYWORDS) + r")\b(.*)$", re.IGNORECASE,
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
                       "O3VALUES", "NOX_VALS"):
            toks = [t.upper() for t in toks]
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


def assert_roundtrip(path: Path) -> int:
    text = path.read_text(encoding="latin-1")
    first = parse_aermod_input(text)
    written = first.to_aermod_input(validate=False)
    second = parse_aermod_input(written)
    assert _wp1_fields(second) == _wp1_fields(first), path.name
    before = _merge_continuations(keyword_lines(text))
    after = _merge_continuations(keyword_lines(written))
    assert after == before, (
        f"{path.name}: keyword lines changed\n  lost: {before - after}\n  gained: {after - before}"
    )
    return sum(before.values())


VENDORED = sorted(FIXTURES.glob("*.inp"))


@pytest.mark.parametrize("path", VENDORED, ids=[p.name for p in VENDORED])
def test_vendored_epa_deck_roundtrips(path):
    assert_roundtrip(path)


def test_vendored_decks_cover_every_keyword_epa_uses():
    """The vendored subset carries every WP-1 keyword form the archive does."""
    seen = set()
    for path in VENDORED:
        seen |= {k for k, _ in keyword_lines(path.read_text(encoding="latin-1"))}
    assert {"MULTYEAR", "NOXVALUE", "OZONEVAL", "OZONEFIL", "MAXDCONT",
            "FILEFORM", "GDSEASON", "GDLANUSE"} <= seen, sorted(seen)


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

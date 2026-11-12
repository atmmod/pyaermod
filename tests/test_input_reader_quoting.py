"""Double-quoted runstream fields, read as AERMOD reads them (setup.f DEFINE).

A field that starts with a double quote runs to the next double quote and
may hold blanks; AERMOD drops the quotes when it opens the file. The reader
keeps such a field whole, quotes included, so the deck writes back as it
was read, and the sandbox judges the path AERMOD would open.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.input_reader import (
    PathTraversalError,
    parse_aermod_input,
    read_aermod_input,
    unquote_path,
)

DECK = """\
CO STARTING
   TITLEONE  quoting test
   MODELOPT  CONC FLAT
   AVERTIME  1
   POLLUTID  SO2
   RUNORNOT  RUN
   ERRORFIL  {errorfil}
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0  0  0
   SRCPARAM  S1  1  10  400  5  1
   SRCGROUP  ALL
SO FINISHED
RE STARTING
   DISCCART  100  0
RE FINISHED
ME STARTING
   SURFFILE  {surf}
   PROFFILE  {prof}
   SURFDATA  14735  1988
   UAIRDATA  14735  1988
   PROFBASE  0.0
ME FINISHED
OU STARTING
   RECTABLE  ALLAVE  FIRST
   SUMMFILE  {summ}
OU FINISHED
"""


def _deck(**kw):
    values = dict(errorfil="err.out", surf="a.sfc", prof="a.pfl", summ="a.sum")
    values.update(kw)
    return DECK.format(**values)


def test_unquote_path_follows_aermod():
    assert unquote_path('"My Met/a.sfc"') == "My Met/a.sfc"
    assert unquote_path('"unterminated name') == "unterminated name"
    assert unquote_path("plain.sfc") == "plain.sfc"
    assert unquote_path('x"y') == 'x"y'          # a quote inside a field is ordinary


def test_a_quoted_file_name_with_blanks_is_one_field_and_writes_back_unchanged():
    project = parse_aermod_input(_deck(surf='"My Met/a.sfc"', summ='"out dir/a.sum"'))
    assert project.meteorology.surface_file == '"My Met/a.sfc"'
    deck = project.to_aermod_input(validate=False)
    assert 'SURFFILE  "My Met/a.sfc"' in deck
    assert 'SUMMFILE  "out dir/a.sum"' in deck


def test_a_quoted_name_in_a_preserved_line_keeps_its_blanks():
    project = parse_aermod_input(_deck(errorfil='"My Dir/err.out"'))
    deck = project.to_aermod_input(validate=False)
    assert '"My Dir/err.out"' in deck
    assert '"My  Dir' not in deck


@pytest.mark.parametrize("field,value", [
    ("surf", '"../../etc/passwd"'),
    ("summ", '"../../tmp/evil.sum"'),
    ("errorfil", '"../outside/err.out"'),
])
def test_the_sandbox_judges_the_path_aermod_opens(tmp_path: Path, field, value):
    inp = tmp_path / "deck.inp"
    inp.write_text(_deck(**{field: value}))
    with pytest.raises(PathTraversalError):
        read_aermod_input(inp, sandbox=True)


def test_a_quoted_name_inside_the_root_passes_the_sandbox(tmp_path: Path):
    inp = tmp_path / "deck.inp"
    inp.write_text(_deck(surf='"My Met/a.sfc"'))
    project = read_aermod_input(inp, sandbox=True)
    assert project.meteorology.surface_file == '"My Met/a.sfc"'


def test_anchoring_a_met_file_in_a_folder_with_blanks_quotes_it(tmp_path: Path):
    from pyaermod.input_reader import anchor_input_files, input_files

    folder = tmp_path / "my run"
    folder.mkdir()
    (folder / "deck.inp").write_text(_deck())
    (folder / "a.sfc").write_text("x")
    project = read_aermod_input(folder / "deck.inp")
    anchor_input_files(project, folder)
    assert project.meteorology.surface_file == f'"{folder / "a.sfc"}"'
    assert f'SURFFILE  "{folder / "a.sfc"}"' in project.to_aermod_input(validate=False)
    # Listed as the file AERMOD opens, without the quotes.
    assert str(folder / "a.sfc") in [ref.path for ref in input_files(project)]

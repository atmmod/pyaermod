"""Sandbox-mode tests for read_aermod_input.

When ingesting untrusted .inp files, callers can pass sandbox=True to
have the reader reject any path that would resolve outside the .inp's
parent directory. This catches both absolute-path escapes (/etc/passwd,
C:\\Windows\\System32\\...) and relative-path escapes (../../etc/passwd).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.input_reader import (
    PathTraversalError,
    parse_aermod_input,
    read_aermod_input,
)

_MINIMAL_INP_TMPL = """\
CO STARTING
   TITLEONE  sandbox test
   MODELOPT  CONC ELEVATED DFAULT
   AVERTIME  ANNUAL
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0  0
   SRCPARAM  S1  1  10  400  5  1
SO FINISHED
RE STARTING
   DISCCART  0  0  0
RE FINISHED
ME STARTING
   SURFFILE  {surf}
   PROFFILE  {prof}
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  0.0
ME FINISHED
OU STARTING
OU FINISHED
"""


def _write(tmp_path: Path, surf: str, prof: str) -> Path:
    inp = tmp_path / "test.inp"
    inp.write_text(_MINIMAL_INP_TMPL.format(surf=surf, prof=prof))
    return inp


class TestSandbox:
    def test_default_off_allows_anything(self, tmp_path):
        """Without sandbox=, escape paths still parse — backwards compat."""
        inp = _write(tmp_path, "/etc/passwd", "../../some.pfl")
        project = read_aermod_input(inp)
        assert project.meteorology.surface_file == "/etc/passwd"

    def test_absolute_escape_caught(self, tmp_path):
        inp = _write(tmp_path, "/etc/passwd", "rel.pfl")
        with pytest.raises(PathTraversalError, match="surface_file"):
            read_aermod_input(inp, sandbox=True)

    def test_relative_escape_caught(self, tmp_path):
        inp = _write(tmp_path, "rel.sfc", "../../../shadow")
        with pytest.raises(PathTraversalError, match="profile_file"):
            read_aermod_input(inp, sandbox=True)

    def test_relative_within_base_passes(self, tmp_path):
        """Sibling files (same dir as the .inp) are fine."""
        inp = _write(tmp_path, "stn.sfc", "stn.pfl")
        project = read_aermod_input(inp, sandbox=True)
        assert project.meteorology.surface_file == "stn.sfc"

    def test_absolute_path_within_base_passes(self, tmp_path):
        """Absolute paths INSIDE the sandbox base are fine."""
        sfc = tmp_path / "data" / "stn.sfc"
        sfc.parent.mkdir(parents=True)
        sfc.write_text("placeholder")
        inp = _write(tmp_path, str(sfc), "stn.pfl")
        # Should not raise
        read_aermod_input(inp, sandbox=True)

    def test_postfile_path_checked(self, tmp_path):
        body = (
            _MINIMAL_INP_TMPL.format(surf="rel.sfc", prof="rel.pfl")
            .replace("OU STARTING", "OU STARTING\n   POSTFILE  1 ALL PLOT  /tmp/escape.pst")
        )
        inp = tmp_path / "test.inp"
        inp.write_text(body)
        with pytest.raises(PathTraversalError, match=r"output\.postfile"):
            read_aermod_input(inp, sandbox=True)


class TestParseAermodInputUnchanged:
    """parse_aermod_input (the in-memory variant) doesn't check paths;
    sandbox is a read_aermod_input-level concern. Pin that contract."""

    def test_parse_aermod_input_no_sandbox_kwarg(self):
        # Parse direct from text — never touches the filesystem
        project = parse_aermod_input(_MINIMAL_INP_TMPL.format(
            surf="/etc/passwd", prof="../../boom.pfl"))
        assert project.meteorology.surface_file == "/etc/passwd"


class TestSandboxCoversNewFilePaths:
    """Every path the reader now stores structurally is checked too."""

    _CO = ("   SAVEFILE  {p}\n", "   INITFILE  {p}\n", "   MULTYEAR  {p}\n",
           "   MULTYEAR  ok.sav  {p}\n", "   NOX_FILE  {p}\n",
           "   NOXSECTR  0  180\n   NOX_FILE  SECT2  {p}\n",
           "   O3SECTOR  0  180\n   OZONEFIL  SECT1  {p}\n")
    _OU = ("   MAXDAILY  ALL  {p}\n", "   MXDYBYYR  ALL  {p}\n",
           "   MAXDCONT  ALL  8  8  {p}\n", "   MAXDCONT  ALL  8  THRESH  1.0  {p}\n")

    @pytest.mark.parametrize("co_line", _CO)
    def test_control_paths_escaping_are_rejected(self, tmp_path, co_line):
        text = _MINIMAL_INP_TMPL.format(surf="a.sfc", prof="a.pfl").replace(
            "   POLLUTID  SO2\n", "   POLLUTID  NO2\n   MODELOPT  CONC GRSM\n"
            + co_line.format(p="../../escape.dat"))
        inp = tmp_path / "t.inp"
        inp.write_text(text)
        with pytest.raises(PathTraversalError):
            read_aermod_input(inp, sandbox=True)
        inp.write_text(text.replace("../../escape.dat", "inside.dat"))
        read_aermod_input(inp, sandbox=True)

    @pytest.mark.parametrize("ou_line", _OU)
    def test_output_paths_escaping_are_rejected(self, tmp_path, ou_line):
        text = _MINIMAL_INP_TMPL.format(surf="a.sfc", prof="a.pfl").replace(
            "OU STARTING\n", "OU STARTING\n" + ou_line.format(p="/etc/escape.dat"))
        inp = tmp_path / "t.inp"
        inp.write_text(text)
        with pytest.raises(PathTraversalError):
            read_aermod_input(inp, sandbox=True)


class TestSandboxReportsEveryEscape:
    """The error lists every escaping path, so a caller can report them all."""

    def test_violations_name_each_field_and_path_as_written(self, tmp_path):
        from pyaermod.input_reader import SandboxViolation

        body = _MINIMAL_INP_TMPL.format(surf="../met/stn.sfc", prof="inside.pfl").replace(
            "OU STARTING", "OU STARTING\n   POSTFILE  1 ALL PLOT  /tmp/escape.pst")
        inp = tmp_path / "test.inp"
        inp.write_text(body)
        with pytest.raises(PathTraversalError, match="surface_file") as caught:
            read_aermod_input(inp, sandbox=True)
        violations = caught.value.violations
        assert [(v.field, v.path) for v in violations] == [
            ("meteorology.surface_file", "../met/stn.sfc"),
            ("output.postfile", "/tmp/escape.pst"),
        ]
        assert all(isinstance(v, SandboxViolation) for v in violations)
        assert violations[0].resolved == (tmp_path / ".." / "met" / "stn.sfc").resolve()

    def test_the_message_still_names_the_first_escape(self, tmp_path):
        inp = _write(tmp_path, "/etc/passwd", "../../shadow")
        with pytest.raises(PathTraversalError) as caught:
            read_aermod_input(inp, sandbox=True)
        message = str(caught.value)
        assert message.startswith("meteorology.surface_file resolves to ")
        assert "profile_file" not in message
        assert len(caught.value.violations) == 2

    def test_a_bare_error_has_no_violations(self):
        assert PathTraversalError("somewhere").violations == ()


def _with_lines(tmp_path: Path, **extra: str) -> Path:
    """The minimal deck with ``extra[pathway]`` added after its STARTING line."""
    body = _MINIMAL_INP_TMPL.format(surf="inside.sfc", prof="inside.pfl")
    for pathway, lines in extra.items():
        body = body.replace(f"{pathway} STARTING", f"{pathway} STARTING\n{lines}", 1)
    inp = tmp_path / "test.inp"
    inp.write_text(body)
    return inp


class TestSandboxCoversLinesKeptAsWritten:
    """A line the reader keeps verbatim is written back as it stands, and
    several such lines name files AERMOD opens: the sandbox checks them."""

    @pytest.mark.parametrize("pathway, line, path", [
        ("CO", "   ERRORFIL  /tmp/elsewhere/errors.out", "/tmp/elsewhere/errors.out"),
        ("CO", "   DEBUGOPT  MODEL  ../debug.out", "../debug.out"),
        ("SO", "   INCLUDED  ../../sources.dat", "../../sources.dat"),
        ("SO", "   HOUREMIS  /data/hourly.emi  S1", "/data/hourly.emi"),
        ("SO", "   BACKGRND  HOURLY  ../bg.dat", "../bg.dat"),
        ("RE", "   INCLUDED  /etc/receptors.dat", "/etc/receptors.dat"),
        ("OU", "   POSTFILE  1  ALL  PLOT  in.pst\n   POSTFILE  3  ALL  PLOT  ../out.pst",
         "../out.pst"),
    ], ids=["errorfil", "debugopt", "so-included", "houremis", "backgrnd-hourly",
            "re-included", "second-postfile"])
    def test_an_escaping_file_on_a_kept_line_is_refused(self, tmp_path, pathway, line, path):
        inp = _with_lines(tmp_path, **{pathway: line})
        project = read_aermod_input(inp)                # read as it stands without
        assert any(path in u.raw for u in project.unparsed_lines)
        with pytest.raises(PathTraversalError) as caught:
            read_aermod_input(inp, sandbox=True)
        (violation,) = caught.value.violations
        assert violation.path == path
        kept = next(u for u in project.unparsed_lines if path in u.raw)
        assert violation.field == f"{kept.pathway} {kept.keyword} at line {kept.lineno}"

    def test_a_quoted_name_with_blanks_is_read_as_one_field(self, tmp_path):
        inp = _with_lines(tmp_path, CO='   ERRORFIL  "sub dir/../../errors.out"')
        with pytest.raises(PathTraversalError) as caught:
            read_aermod_input(inp, sandbox=True)
        # One field, blanks and all (the writer joins the reader's tokens
        # with two blanks, so the name comes back with two).
        (violation,) = caught.value.violations
        assert violation.path.split() == ["sub", "dir/../../errors.out"]

    def test_kept_lines_inside_the_folder_are_accepted(self, tmp_path):
        inp = _with_lines(
            tmp_path,
            CO="   ERRORFIL  errors.out\n   DEBUGOPT  MODEL  sub/debug.out",
            SO="   INCLUDED  sources/../more.dat\n   ELEVUNIT  METERS",
            ME="   SITEDATA  99999  1988  HUDSON",
        )
        project = read_aermod_input(inp, sandbox=True)
        assert len(project.unparsed_lines) == 5

    def test_the_recorded_aertest_deck_is_accepted(self, tmp_path):
        """Numbers, IDs and option words on kept lines are not paths out."""
        deck = (Path(__file__).parent / "fixtures" / "gui" / "aermod_recordings"
                / "aertest" / "aertest.inp")
        copy = tmp_path / "aertest.inp"
        copy.write_text(deck.read_text())
        project = read_aermod_input(copy, sandbox=True)
        assert [u.keyword for u in project.unparsed_lines] == [
            "ERRORFIL", "ELEVUNIT", "SITEDATA"]

    def test_a_name_the_file_system_cannot_resolve_is_refused(self, tmp_path):
        from pyaermod.input_reader import _validate_paths_within

        project = read_aermod_input(_with_lines(tmp_path, CO="   ERRORFIL  errors.out"))
        project.unparsed_lines[0].fields[0] = "bad\x00name"
        with pytest.raises(PathTraversalError) as caught:
            _validate_paths_within(project, tmp_path)
        assert [v.path for v in caught.value.violations] == ["bad\x00name"]


class TestRunstreamFields:
    """Fields split as AERMOD's DEFINE splits them (setup.f)."""

    @pytest.mark.parametrize("text, fields", [
        ("", []),
        ("  a   b  ", ["a", "b"]),
        ('"My Files/a.dat"  2', ["My Files/a.dat", "2"]),
        ('x"y  z', ['x"y', "z"]),
        ('"unterminated name', ["unterminated name"]),
        ('""  a', ["", "a"]),
        ("a\tb", ["a", "b"]),
    ])
    def test_cases(self, text, fields):
        from pyaermod.input_reader import runstream_fields

        assert runstream_fields(text) == fields

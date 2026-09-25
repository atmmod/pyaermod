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

"""CO DEBUGOPT, the MODELOPT depletion switches, and the terrain option
the receptor writer is given.

The field layouts come from AERMOD v26135: coset.f DEBOPT (DEBUGOPT) and
coset.f MODOPT with soset.f (DRYDPLT / NODRYDPLT / WETDPLT / NOWETDPLT).
The same options run on the binary in
tests/test_receptor_deck_acceptance.py.
"""

from __future__ import annotations

import pytest

from pyaermod.input_reader import (
    PathTraversalError,
    parse_aermod_input,
    read_aermod_input,
)
from pyaermod.pathways import DEBUG_OPTIONS, ControlPathway, TerrainType
from pyaermod.sources import DepositionMethod


def _ctl(**kw) -> ControlPathway:
    kw.setdefault("title_one", "d4")
    return ControlPathway(**kw)


def _lines(text: str, keyword: str) -> list[str]:
    return [ln.split(None, 1)[1] for ln in text.splitlines() if ln.split()[:1] == [keyword]]


# ---------------------------------------------------------------------------
# CO DEBUGOPT
# ---------------------------------------------------------------------------

class TestDebugOptions:
    def test_no_options_write_no_line(self):
        assert "DEBUGOPT" not in _ctl().to_aermod_input()

    def test_line_is_written_after_modelopt_as_given(self):
        text = _ctl(debug_options=["MODEL", "Model.Dbg", "DEPOS"]).to_aermod_input()
        keywords = [ln.split()[0] for ln in text.splitlines()]
        # DEBOPT checks DEPOS against MODELOPT, so MODELOPT must come first.
        assert keywords.index("MODELOPT") < keywords.index("DEBUGOPT") < keywords.index("RUNORNOT")
        assert _lines(text, "DEBUGOPT") == ["MODEL  Model.Dbg  DEPOS"]

    def test_debug_files_are_the_fields_that_are_not_options(self):
        control = _ctl(debug_options=["model", "run/m.dbg", "AREA", "DEPOS", "PRIME", "p.dbg"])
        assert control.debug_files() == ["run/m.dbg", "p.dbg"]

    def test_option_names_are_coset_debugopt_array(self):
        # coset.f DEBUGOPT_ARRAY, v26135: 23 names, LINE among them.
        assert len(DEBUG_OPTIONS) == 23
        assert {"MODEL", "METEOR", "AREA", "LINE", "DEPOS", "PRIME", "VBARRIER"} <= set(DEBUG_OPTIONS)

    def test_reader_keeps_the_fields_and_their_case(self):
        project = parse_aermod_input(_deck(co="   DEBUGOPT  AREA  DEPOS  MODEL  Out/Model.Dbg\n"))
        assert project.control.debug_options == ["AREA", "DEPOS", "MODEL", "Out/Model.Dbg"]
        assert not [ln for ln in project.unparsed_lines if "DEBUGOPT" in str(ln)]
        rewritten = project.to_aermod_input(validate=False)
        assert _lines(rewritten, "DEBUGOPT") == ["AREA  DEPOS  MODEL  Out/Model.Dbg"]

    def test_reader_pools_repeated_cards(self):
        # v26135 DEBOPT pools the fields of every DEBUGOPT card.
        project = parse_aermod_input(_deck(co="   DEBUGOPT  MODEL\n   DEBUGOPT  DEPOS\n"))
        assert project.control.debug_options == ["MODEL", "DEPOS"]

    def test_bare_debugopt_is_kept_verbatim(self):
        project = parse_aermod_input(_deck(co="   DEBUGOPT\n"))
        assert project.control.debug_options == []
        assert [ln for ln in project.unparsed_lines if "DEBUGOPT" in str(ln)]

    def test_sandbox_checks_debug_file_names(self, tmp_path):
        inp = tmp_path / "t.inp"
        inp.write_text(_deck(co="   DEBUGOPT  MODEL  ../../escape.dbg\n"))
        with pytest.raises(PathTraversalError, match="debug_options"):
            read_aermod_input(inp, sandbox=True)
        inp.write_text(_deck(co="   DEBUGOPT  MODEL  inside.dbg  DEPOS\n"))
        assert read_aermod_input(inp, sandbox=True).control.debug_files() == ["inside.dbg"]


# ---------------------------------------------------------------------------
# MODELOPT DRYDPLT / NODRYDPLT / WETDPLT / NOWETDPLT
# ---------------------------------------------------------------------------

class TestDepletion:
    @pytest.mark.parametrize(("dry", "wet", "tokens"), [
        (None, None, []),
        (True, None, ["DRYDPLT"]),
        (False, None, ["NODRYDPLT"]),
        (None, True, ["WETDPLT"]),
        (None, False, ["NOWETDPLT"]),
        (False, False, ["NODRYDPLT", "NOWETDPLT"]),
    ])
    def test_tokens(self, dry, wet, tokens):
        control = _ctl(calculate_deposition=True, dry_depletion=dry, wet_depletion=wet)
        opts = _lines(control.to_aermod_input(), "MODELOPT")[0].split()
        assert [t for t in opts if "DPLT" in t] == tokens

    @pytest.mark.parametrize(("token", "attr", "value"), [
        ("DRYDPLT", "dry_depletion", True),
        ("NODRYDPLT", "dry_depletion", False),
        ("WETDPLT", "wet_depletion", True),
        ("NOWETDPLT", "wet_depletion", False),
    ])
    def test_reader_fills_the_field(self, token, attr, value):
        project = parse_aermod_input(_deck(modelopt=f"CONC FLAT {token}"))
        assert getattr(project.control, attr) is value
        assert token not in project.control.extra_model_options
        assert token in _lines(project.to_aermod_input(validate=False), "MODELOPT")[0].split()

    def test_conflicting_tokens_are_written_back(self):
        # DRYDPLT NODRYDPLT is AERMOD's E149; the deck keeps both so the
        # rewrite fails the same way instead of silently picking one.
        project = parse_aermod_input(_deck(modelopt="CONC FLAT DRYDPLT NODRYDPLT"))
        assert project.control.dry_depletion is True
        assert project.control.extra_model_options == ["NODRYDPLT"]
        opts = _lines(project.to_aermod_input(validate=False), "MODELOPT")[0].split()
        assert "DRYDPLT" in opts and "NODRYDPLT" in opts


def test_deposition_method_enum_is_documented_as_inert():
    """DepositionMethod stays for compatibility; its docstring says why."""
    doc = DepositionMethod.__doc__ or ""
    assert "no ``METHOD`` keyword" in doc
    assert "dry_depletion" in doc and "wet_depletion" in doc


# ---------------------------------------------------------------------------
# Terrain as AERMOD resolves it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(("terrain", "dfault", "elevated"), [
    (TerrainType.FLAT, True, True),       # W206: DFAULT overrides FLAT
    (TerrainType.FLAT, False, False),
    (TerrainType.ELEVATED, False, True),
    (TerrainType.FLATSRCS, False, True),  # FLAT ELEV: elevated receptors
])
def test_elevated_terrain(terrain, dfault, elevated):
    control = _ctl(terrain_type=terrain, regulatory_default=dfault)
    assert control.elevated_terrain is elevated


def _deck(*, modelopt: str = "CONC FLAT", co: str = "", re: str = "   DISCCART  0.0  100.0\n") -> str:
    return (
        "CO STARTING\n   TITLEONE  d4\n"
        f"   MODELOPT  {modelopt}\n   AVERTIME  1\n   POLLUTID  OTHER\n{co}"
        "   RUNORNOT  RUN\nCO FINISHED\n"
        "SO STARTING\n   LOCATION  S1  POINT  0.0  0.0  0.0\n"
        "   SRCPARAM  S1  1.0  20.0  400.0  10.0  1.0\n   SRCGROUP  ALL\nSO FINISHED\n"
        f"RE STARTING\n{re}RE FINISHED\n"
        "ME STARTING\n   SURFFILE  a.sfc\n   PROFFILE  a.pfl\n   SURFDATA  1  2020\n"
        "   UAIRDATA  1  2020\n   PROFBASE  0.0\nME FINISHED\n"
        "OU STARTING\n   RECTABLE  ALLAVE  FIRST\nOU FINISHED\n"
    )

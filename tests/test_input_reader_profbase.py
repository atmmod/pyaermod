"""PROFBASE keeps its units (review H5).

``PROFBASE elev [METERS|FEET]`` (meset.f): AERMOD converts a FEET value
to metres. pyaermod's ``profile_base_elevation`` is in metres, so the
reader converts too; it used to keep the number and drop the unit, which
turned ``328 FEET`` into ``328 METERS``.
"""

from __future__ import annotations

import pytest

from pyaermod.input_reader import parse_aermod_input


def _deck(profbase: str) -> str:
    return f"""\
CO STARTING
   TITLEONE  t
   MODELOPT  CONC FLAT
   AVERTIME  1
   POLLUTID  SO2
CO FINISHED
SO STARTING
   LOCATION  S1  POINT  0.0  0.0  0.0
   SRCPARAM  S1  1.0  30.0  400.0  10.0  2.0
   SRCGROUP  ALL
SO FINISHED
RE STARTING
   DISCCART  100.0  0.0
RE FINISHED
ME STARTING
   SURFFILE  a.sfc
   PROFFILE  a.pfl
   SURFDATA  1  2020
   UAIRDATA  1  2020
   PROFBASE  {profbase}
ME FINISHED
OU STARTING
   RECTABLE  ALLAVE  FIRST
OU FINISHED
"""


@pytest.mark.parametrize("profbase,metres", [
    ("328.0  FEET", 328.0 * 0.3048),
    ("328.0  feet", 328.0 * 0.3048),
    ("100.0  METERS", 100.0),
    ("100.0", 100.0),
])
def test_profbase_is_read_in_metres(profbase, metres):
    met = parse_aermod_input(_deck(profbase)).meteorology
    assert met.profile_base_elevation == pytest.approx(metres)


def test_profbase_in_feet_is_written_as_the_same_height_in_metres():
    project = parse_aermod_input(_deck("328.0  FEET"))
    line = next(ln for ln in project.meteorology.to_aermod_input().splitlines()
                if "PROFBASE" in ln)
    value, units = line.split()[1:]
    assert units == "METERS"
    assert float(value) == pytest.approx(328.0 * 0.3048, abs=1e-6)


def test_profbase_rewrite_reads_back_unchanged():
    project = parse_aermod_input(_deck("328.0  FEET"))
    again = parse_aermod_input(project.to_aermod_input())
    assert again.meteorology.profile_base_elevation == pytest.approx(
        project.meteorology.profile_base_elevation, abs=1e-9)


def test_profbase_with_one_decimal_is_still_written_with_one():
    met = parse_aermod_input(_deck("0.0  METERS")).meteorology
    assert "PROFBASE  0.0  METERS" in met.to_aermod_input()


# ----------------------------------------------------------------------
# A unit other than METERS/FEET (meset.f PRBASE: W203, value taken as
# metres; AERMOD probe 33e), a D exponent, and a value that is no number
# ----------------------------------------------------------------------

def test_an_unknown_unit_is_read_as_metres_with_a_warning(caplog):
    with caplog.at_level("WARNING", logger="pyaermod.input_reader"):
        project = parse_aermod_input(_deck("100.0  YARDS"))
    assert project.meteorology.profile_base_elevation == 100.0
    assert project.unparsed_lines == []
    messages = [r.getMessage() for r in caplog.records if "PROFBASE" in r.getMessage()]
    assert len(messages) == 1, messages
    assert "W203" in messages[0] and "YARDS" in messages[0] and "metres" in messages[0]
    assert "line " in messages[0]


@pytest.mark.parametrize("profbase", ["100.0  METERS", "328.0  FEET", "100.0"])
def test_a_known_unit_gives_no_warning(caplog, profbase):
    with caplog.at_level("WARNING", logger="pyaermod.input_reader"):
        parse_aermod_input(_deck(profbase))
    assert not [r for r in caplog.records if "PROFBASE" in r.getMessage()]


def test_a_fortran_d_exponent_is_read():
    met = parse_aermod_input(_deck("1.5D2  METERS")).meteorology
    assert met.profile_base_elevation == 150.0


@pytest.mark.parametrize("profbase", ["abc  METERS", "1x0  FEET", "abc"])
def test_a_value_that_is_no_number_is_an_error_naming_the_line(profbase):
    # Kept verbatim, it was written beside the PROFBASE card the
    # MeteorologyPathway always writes (two PROFBASE cards, on top of
    # E208), and removing it silently gave 0 m. AERMOD stops with E208,
    # so the reader stops too, as for SURFDATA/UAIRDATA (review finding 4).
    lineno = _deck(profbase).splitlines().index(f"   PROFBASE  {profbase}") + 1
    with pytest.raises(ValueError) as excinfo:
        parse_aermod_input(_deck(profbase))
    message = str(excinfo.value)
    assert f"line {lineno}" in message
    assert "PROFBASE" in message and "E208" in message
    assert repr(profbase.split()[0]) in message


@pytest.mark.parametrize("feet", [1234.567, 328.1, 0.1, 99999.99, 1.0 / 3.0])
def test_profbase_written_from_feet_reads_back_exactly(feet):
    project = parse_aermod_input(_deck(f"{feet!r}  FEET"))
    base = project.meteorology.profile_base_elevation
    again = parse_aermod_input(project.to_aermod_input())
    assert again.meteorology.profile_base_elevation == base


@pytest.mark.parametrize("base", [376.29602160000003, 1.0 / 3.0, 1e-7, 123456789.123])
def test_any_profbase_in_metres_reads_back_exactly(base):
    from pyaermod.pathways import MeteorologyPathway
    met = MeteorologyPathway(surface_file="a.sfc", profile_file="a.pfl",
                             profile_base_elevation=base)
    line = next(ln for ln in met.to_aermod_input().splitlines() if "PROFBASE" in ln)
    assert float(line.split()[1]) == base

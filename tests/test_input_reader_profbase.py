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

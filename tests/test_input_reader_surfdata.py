"""SURFDATA and UAIRDATA fields written as reals, as AERMOD accepts them."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.input_reader import parse_aermod_input, read_aermod_input

FIXTURE = Path(__file__).parent / "fixtures" / "runner" / "success" / "aermod.inp"


def _deck(surfdata: str, uairdata: str = "UAIRDATA  14735  1988") -> str:
    text = FIXTURE.read_text()
    lines = []
    for line in text.splitlines():
        key = line.split()[0] if line.split() else ""
        if key == "SURFDATA":
            line = f"   {surfdata}"
        elif key == "UAIRDATA":
            line = f"   {uairdata}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def test_the_runner_fixture_aermod_ran_is_read():
    """AERMOD ran this deck (its .out echoes station 14735); the reader used to raise."""
    project = read_aermod_input(FIXTURE)
    assert project.meteorology.surface_station_id == 14735
    assert isinstance(project.meteorology.surface_station_id, int)


def test_real_station_and_year_become_whole_numbers():
    project = parse_aermod_input(_deck("SURFDATA  14735.0  1988.0", "UAIRDATA  14735.0  1988.0"))
    met = project.meteorology
    assert (met.surface_station_id, met.data_start_year, met.upper_air_station_id) == (14735, 1988, 14735)
    assert "SURFDATA  14735  1988" in project.to_aermod_input(validate=False)


@pytest.mark.parametrize("card", ["SURFDATA  KALB  1988", "SURFDATA  14735  1988.5"])
def test_a_field_that_is_not_a_whole_number_is_an_error_naming_the_line(card):
    with pytest.raises(ValueError, match=r"line \d+: SURFDATA"):
        parse_aermod_input(_deck(card))

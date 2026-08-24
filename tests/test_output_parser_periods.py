"""Averaging-period detection in the AERMOD output parser.

Regression for a substring match: the ``4-HR`` pattern also matched inside
``24-HR`` section headers, so every deck with a 24-hour average grew a
phantom ``4HR`` result that duplicated the 24-hour table. Surfaced by
``tests/test_epa_cases.py`` once EPA's archive became available in CI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyaermod.output_parser import AERMODOutputParser

FIXT = Path(__file__).parent / "fixtures" / "epa_official"


def test_aertest_periods_have_no_phantom_4hr():
    """AERTEST runs AVERTIME 1 3 8 24 PERIOD — exactly those five."""
    results = AERMODOutputParser(FIXT / "AERTEST.SUM").parse()
    assert set(results.concentrations) == {"1HR", "3HR", "8HR", "24HR", "PERIOD"}
    assert "4HR" not in results.concentrations
    assert results.concentrations["24HR"].max_value == pytest.approx(88.89517, abs=1e-3)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("*** THE SUMMARY OF HIGHEST 24-HR RESULTS ***", {"24HR"}),
        ("*** THE SUMMARY OF HIGHEST  4-HR RESULTS ***", {"4HR"}),
        ("*** THE SUMMARY OF HIGHEST 12-HR RESULTS ***", {"12HR"}),
        ("*** THE SUMMARY OF HIGHEST  2-HR RESULTS ***", {"2HR"}),
        ("*** THE SUMMARY OF HIGHEST  1-HR RESULTS ***", {"1HR"}),
    ],
)
def test_period_header_matches_whole_number_only(tmp_path, header, expected):
    out = tmp_path / "run.out"
    out.write_text(
        " *** AERMOD - VERSION 26135  ***   *** synthetic ***        08/22/26\n"
        "\n"
        f"{header}\n"
        "\n"
        "GROUP ID   AVERAGE CONC   RECEPTOR  (XR, YR, ZELEV, ZHILL, ZFLAG)  OF TYPE  GRID-ID\n"
        "ALL       1ST HIGHEST VALUE IS      10.00000 AT (     100.00,     200.00,     0.00,     0.00,    0.00)  DC\n"
        "          2ND HIGHEST VALUE IS       9.00000 AT (     110.00,     210.00,     0.00,     0.00,    0.00)  DC\n"
        "\n"
        " *** AERMOD Finishes Successfully ***\n",
        encoding="latin-1",
    )
    results = AERMODOutputParser(out).parse()
    assert set(results.concentrations) == expected

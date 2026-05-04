"""
US National Ambient Air Quality Standards (NAAQS) reference table.

Constants reflect the standards in effect as of the 2024 EPA NAAQS
review. Concentration units are micrograms per cubic meter (µg/m³)
for particulate matter and parts per billion (ppb) for gaseous
pollutants, mirroring 40 CFR Part 50.

For each pollutant the entry encodes:

- ``averaging_period`` — averaging period of the standard
- ``form`` — statistical form ("annual", "98th percentile", etc.)
- ``level`` — numeric standard
- ``units`` — "ug/m3" or "ppb"
- ``cfr_reference`` — 40 CFR Part 50 subpart citation

This is a *reference* table only. Per-pollutant design-value math
lives in :mod:`pyaermod.design_values`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NAAQSStandard:
    """One NAAQS row."""
    pollutant: str
    averaging_period: str
    form: str
    level: float
    units: str
    cfr_reference: str


# Note: PM2.5 24-hr was 35 µg/m³ before 2024; PM2.5 annual was lowered
# from 12 to 9 in 2024. PM10 annual was revoked in 2006. Reflecting
# current standards as of the most recent review.

NAAQS_TABLE: dict[str, list[NAAQSStandard]] = {
    "PM2.5": [
        NAAQSStandard("PM2.5", "annual", "annual mean", 9.0, "ug/m3",
                      "40 CFR 50.18"),
        NAAQSStandard("PM2.5", "24-hour", "98th percentile", 35.0, "ug/m3",
                      "40 CFR 50.18"),
    ],
    "PM10": [
        NAAQSStandard("PM10", "24-hour", "not exceeded > 1/yr (5-yr avg)",
                      150.0, "ug/m3", "40 CFR 50.6"),
    ],
    "NO2": [
        NAAQSStandard("NO2", "annual", "annual mean", 53.0, "ppb",
                      "40 CFR 50.11"),
        NAAQSStandard("NO2", "1-hour", "98th percentile of daily max",
                      100.0, "ppb", "40 CFR 50.11"),
    ],
    "SO2": [
        NAAQSStandard("SO2", "1-hour", "99th percentile of daily max",
                      75.0, "ppb", "40 CFR 50.17"),
    ],
    "CO": [
        NAAQSStandard("CO", "1-hour",
                      "not exceeded more than once per year",
                      35_000.0, "ppb", "40 CFR 50.8"),
        NAAQSStandard("CO", "8-hour",
                      "not exceeded more than once per year",
                      9_000.0, "ppb", "40 CFR 50.8"),
    ],
    "O3": [
        NAAQSStandard("O3", "8-hour", "annual 4th-highest daily max (3-yr avg)",
                      70.0, "ppb", "40 CFR 50.19"),
    ],
    "Pb": [
        NAAQSStandard("Pb", "rolling 3-month",
                      "rolling 3-month avg max", 0.15, "ug/m3",
                      "40 CFR 50.16"),
    ],
}


def get_naaqs(pollutant: str, averaging_period: str) -> NAAQSStandard:
    """Look up the NAAQS for a (pollutant, averaging_period) pair.

    Raises
    ------
    KeyError
        If the pollutant or averaging period is not in the table.
    """
    rows = NAAQS_TABLE.get(pollutant.upper())
    if rows is None:
        raise KeyError(f"No NAAQS entries for pollutant {pollutant!r}")
    for r in rows:
        if r.averaging_period.lower() == averaging_period.lower():
            return r
    raise KeyError(
        f"No NAAQS entry for {pollutant} averaging_period={averaging_period!r}; "
        f"available: {[r.averaging_period for r in rows]}"
    )


__all__ = ["NAAQS_TABLE", "NAAQSStandard", "get_naaqs"]

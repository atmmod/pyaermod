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
    """One NAAQS row.

    ``percentile`` is set for the standards whose design value is an
    annual percentile of daily values read off a rank table (40 CFR 50
    appendices N, S and T); :meth:`design_rank` turns it into the rank
    AERMOD's MAXDCONT/MXDYBYYR outputs and the design-value functions in
    :mod:`pyaermod.design_values` work with.
    """
    pollutant: str
    averaging_period: str
    form: str
    level: float
    units: str
    cfr_reference: str
    percentile: float | None = None

    def design_rank(self, n_days: int = 366) -> int:
        """Rank (1 = highest) of this standard's percentile in a year.

        The rank comes from the appendix tables via
        :func:`pyaermod.design_values.naaqs_percentile_rank`; for a full
        year that is the 8th-highest daily value for the 98th percentile
        (1-hour NO2, 24-hour PM2.5) and the 4th-highest for the 99th
        (1-hour SO2). Raises ``ValueError`` for a standard whose form is
        not a percentile.
        """
        if self.percentile is None:
            raise ValueError(
                f"the {self.pollutant} {self.averaging_period} NAAQS is not "
                f"a percentile form ({self.form}); it has no design rank"
            )
        from .design_values import naaqs_percentile_rank  # avoid a cycle
        return naaqs_percentile_rank(n_days, self.percentile)


# Note: PM2.5 24-hr was 35 µg/m³ before 2024; PM2.5 annual was lowered
# from 12 to 9 in 2024. PM10 annual was revoked in 2006. Reflecting
# current standards as of the most recent review.

NAAQS_TABLE: dict[str, list[NAAQSStandard]] = {
    "PM2.5": [
        NAAQSStandard("PM2.5", "annual", "annual mean", 9.0, "ug/m3",
                      "40 CFR 50.18"),
        NAAQSStandard("PM2.5", "24-hour", "98th percentile", 35.0, "ug/m3",
                      "40 CFR 50.18", percentile=98.0),
    ],
    "PM10": [
        NAAQSStandard("PM10", "24-hour", "not exceeded > 1/yr (5-yr avg)",
                      150.0, "ug/m3", "40 CFR 50.6"),
    ],
    "NO2": [
        NAAQSStandard("NO2", "annual", "annual mean", 53.0, "ppb",
                      "40 CFR 50.11"),
        NAAQSStandard("NO2", "1-hour", "98th percentile of daily max",
                      100.0, "ppb", "40 CFR 50.11", percentile=98.0),
    ],
    "SO2": [
        NAAQSStandard("SO2", "1-hour", "99th percentile of daily max",
                      75.0, "ppb", "40 CFR 50.17", percentile=99.0),
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
    # Table keys are the conventional spellings ("PM2.5", "Pb"), so match
    # case-insensitively rather than upper-casing the caller's string --
    # "Pb".upper() is "PB", which is not a key.
    key = pollutant.strip().upper()
    rows = next(
        (v for k, v in NAAQS_TABLE.items() if k.upper() == key), None
    )
    if rows is None:
        raise KeyError(
            f"No NAAQS entries for pollutant {pollutant!r}; "
            f"available: {sorted(NAAQS_TABLE)}"
        )
    for r in rows:
        if r.averaging_period.lower() == averaging_period.lower():
            return r
    raise KeyError(
        f"No NAAQS entry for {pollutant} averaging_period={averaging_period!r}; "
        f"available: {[r.averaging_period for r in rows]}"
    )


__all__ = ["NAAQS_TABLE", "NAAQSStandard", "get_naaqs"]

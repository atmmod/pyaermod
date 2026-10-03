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

    @property
    def level_ugm3(self) -> float:
        """The level in µg/m³, the unit AERMOD reports concentrations in.

        Standards set in ppb are converted with :func:`ppb_to_ugm3` at the
        reference conditions of 40 CFR 50.3 (25 °C, 760 mm Hg): 75 ppb of
        SO2 is 196.4 µg/m³ and 100 ppb of NO2 is 188.0 µg/m³.
        """
        if self.units == "ug/m3":
            return self.level
        if self.units == "ppb":
            return ppb_to_ugm3(self.pollutant, self.level)
        raise ValueError(f"cannot convert {self.units!r} to ug/m3")

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


#: Molecular weights (g/mol) of the gaseous NAAQS pollutants.
MOLECULAR_WEIGHTS: dict[str, float] = {
    "SO2": 64.064,
    "NO2": 46.0055,
    "CO": 28.010,
    "O3": 47.997,
}

#: Volume of a mole of ideal gas (litres) at the reference conditions of
#: 40 CFR 50.3, 25 °C and 760 mm Hg: R * 298.15 K / 101.325 kPa.
MOLAR_VOLUME_L = 24.465


def ppb_to_ugm3(pollutant: str, ppb: float) -> float:
    """Convert a mixing ratio in ppb to a concentration in µg/m³.

    ``µg/m³ = ppb * M / 24.465`` with the molecular weight ``M`` from
    :data:`MOLECULAR_WEIGHTS` and the molar volume at 25 °C and 1 atm
    (40 CFR 50.3). Raises ``KeyError`` for a pollutant that is not a gas
    in the table (particulate matter and lead are set in µg/m³ already).
    """
    key = pollutant.strip().upper()
    if key not in MOLECULAR_WEIGHTS:
        raise KeyError(
            f"no molecular weight for {pollutant!r}; "
            f"available: {sorted(MOLECULAR_WEIGHTS)}"
        )
    return ppb * MOLECULAR_WEIGHTS[key] / MOLAR_VOLUME_L


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


#: The AERMOD ``AVERTIME`` token for each NAAQS averaging period.
_AVERTIME_TOKENS = {
    "1-hour": "1",
    "3-hour": "3",
    "8-hour": "8",
    "24-hour": "24",
    "annual": "ANNUAL",
    "rolling 3-month": "MONTH",
}

#: AERMOD's ``POLLUTID`` spellings that differ from the table's keys.
_POLLUTID_KEYS = {"PM25": "PM2.5", "PB": "Pb"}


def naaqs_averaging_periods(pollutant: str) -> list[str]:
    """The AERMOD averaging periods (``AVERTIME`` tokens) of a pollutant's NAAQS.

    ``pollutant`` is a ``POLLUTID`` (``SO2``, ``PM25``, ...) or a table key
    (``PM2.5``). The periods come in the order AERMOD lists them, short
    ones first: ``["1"]`` for SO2, ``["1", "ANNUAL"]`` for NO2 and
    ``["24", "ANNUAL"]`` for PM2.5. The Pb rolling three-month standard
    maps to ``MONTH``, AERMOD's calendar-month average, which is the input
    to the rolling mean. A pollutant without a NAAQS (``OTHER``) has none.
    """
    key = pollutant.strip().upper()
    key = _POLLUTID_KEYS.get(key, key)
    rows = next((v for k, v in NAAQS_TABLE.items() if k.upper() == key.upper()), [])
    order = list(_AVERTIME_TOKENS.values())
    tokens = {_AVERTIME_TOKENS[r.averaging_period] for r in rows}
    return [t for t in order if t in tokens]


__all__ = [
    "MOLAR_VOLUME_L",
    "MOLECULAR_WEIGHTS",
    "NAAQS_TABLE",
    "NAAQSStandard",
    "get_naaqs",
    "naaqs_averaging_periods",
    "ppb_to_ugm3",
]

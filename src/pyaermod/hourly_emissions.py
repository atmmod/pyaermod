"""
Hourly emission files (``SO HOUREMIS``) of rate-only records.

AERMOD reads a HOUREMIS file one record per source per meteorological
hour (aermod.f HRLOOP): for every hour of the surface file it loops over
the sources in the order the deck defines them and, for each source
named on a ``HOUREMIS`` card, reads the next record of that card's file.
The record's date must equal the met hour (E455) and its source ID the
source being read (E342). A record is free-format fields::

    SO HOUREMIS  yy mm dd hh  srcid  qemis

which is the layout of EPA's ``pset2pa.emi`` (surface coal mine test
case). For AREA, AREACIRC, AREAPOLY, OPENPIT, VOLUME, LINE, RLINE and
RLINEXT sources the rate is the only hourly value HRQREAD needs (eight
fields; the hourly sigmas VOLUME and the AREA and LINE types may add are
optional); a record with no rate (seven fields) is read as zero emission
for that hour with warning W344. POINT and BUOYLINE sources need more
fields per hour and are not written here.

Two pieces live in this module:

* :func:`write_hourly_emissions` writes the records;
* :func:`ap42_wind_profile` builds the hourly wind factor of AP-42
  Section 13.2.4, Equation 1, from an AERMET surface (``.SFC``) file, so
  a batch-drop emission can follow the wind hour by hour.

:meth:`pyaermod.sources.SourcePathway.add_hourly_emissions` combines the
record writer with the ``HOUREMIS`` card in the SO pathway.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

#: One met hour as AERMET's surface file writes it: (year, month, day,
#: hour), hour 1-24. The year is kept as the file has it (two digits in
#: EPA's cordero.sfc, four in AERMET2.SFC); AERMOD reads both alike.
Hour = Tuple[int, int, int, int]

#: AERMOD treats a reference wind speed of 90 m/s or more, or a negative
#: one, as a missing hour (metext.f CHKMSG, UREF .GE. 90 .OR. UREF .LT. 0).
MISSING_WIND_SPEED = 90.0


def _aermod_missing_hour(ustar: float, wstar: float, ziconv: float, zimech: float,
                         obulen: float, uref: float, wdref: float, ta: float) -> bool:
    """Whether AERMOD skips this hour as missing (metext.f METCHK).

    CHKCLM runs first and a calm hour (UREF exactly 0) is never checked
    for missing data; CHKMSG then flags a missing wind speed, direction
    or temperature, a missing Monin-Obukhov length, a missing mixing
    height (the convective one only in a convective hour), or a missing
    u* or w* (w* only in a convective hour).
    """
    if uref == 0.0:
        return False
    return (uref >= MISSING_WIND_SPEED or uref < 0.0
            or wdref > 900.0 or wdref <= -9.0
            or ta > 900.0 or ta <= 0.0
            or obulen < -99990.0
            or (obulen < 0.0 and (ziconv > 90000.0 or ziconv < 0.0))
            or zimech > 90000.0 or zimech < 0.0
            or ustar < 0.0 or ustar >= 9.0
            or (wstar < 0.0 and -99990.0 < obulen < 0.0))


def _check_hour(hour: Sequence[int], index: int) -> Hour:
    if len(hour) != 4:
        raise ValueError(f"hours[{index}] must be (year, month, day, hour), got {hour!r}")
    year, month, day, hr = (int(v) for v in hour)
    if year < 0 or not 1 <= month <= 12 or not 1 <= day <= 31 or not 1 <= hr <= 24:
        raise ValueError(f"hours[{index}] is not a valid (year, month, day, hour 1-24): {hour!r}")
    return year, month, day, hr


def hourly_emission_record(hour: Hour, source_id: str, rate: Optional[float]) -> str:
    """One ``SO HOUREMIS`` record, laid out as EPA's ``pset2pa.emi``.

    ``rate`` None (or NaN) writes the record without a rate, which AERMOD
    reads as zero emission for that hour with warning W344.
    """
    year, month, day, hr = hour
    head = f"SO HOUREMIS {year:>3d}{month:>3d}{day:>3d}{hr:>3d}  "
    if rate is None or math.isnan(rate):
        return head + source_id
    value = float(rate)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(
            f"hourly emission rate of {source_id} at {hour} must be a finite "
            f"number >= 0 (or None for a missing hour), got {rate!r}")
    # 7 significant figures; STODBL needs the decimal point that .6E
    # always writes before its exponent.
    return f"{head}{source_id:<8}  {value:.6E}"


def write_hourly_emissions(path: Union[str, Path],
                           hours: Sequence[Sequence[int]],
                           rates: Mapping[str, Sequence[Optional[float]]]) -> Path:
    """Write a HOUREMIS file of hourly emission rates.

    Parameters
    ----------
    path : str or Path
        File to write.
    hours : sequence of (year, month, day, hour)
        Every hour of the meteorological data AERMOD will read, in file
        order (for instance :attr:`WindEmissionProfile.hours`). AERMOD
        reads one record per source for each of them, including hours
        before a ``STARTEND`` start, and stops the run at the first date
        that differs from the met hour (E455).
    rates : mapping of source ID to a sequence of rates
        The rate of each source for each hour (the SRCPARAM units, e.g.
        g/s for VOLUME, g/(s m^2) for AREA and OPENPIT). Records are written hour by
        hour, and within each hour in the mapping's order, which must
        be the order in which the deck defines these sources (E342
        otherwise). ``None`` or NaN writes a record without a rate:
        zero emission that hour, warning W344.

    Returns
    -------
    Path
        The file written.
    """
    checked = [_check_hour(h, i) for i, h in enumerate(hours)]
    if not rates:
        raise ValueError("rates must name at least one source")
    for source_id, values in rates.items():
        if len(values) != len(checked):
            raise ValueError(
                f"{source_id} has {len(values)} hourly rates for {len(checked)} hours")
    out = [hourly_emission_record(hour, source_id, values[i])
           for i, hour in enumerate(checked)
           for source_id, values in rates.items()]
    target = Path(path)
    target.write_text("\n".join(out) + "\n")
    return target


@dataclass
class WindEmissionProfile:
    """The AP-42 batch-drop wind factor, hour by hour, for one met file.

    AP-42 Section 13.2.4, Equation 1 (rating A) scales the emission
    factor of aggregate handling with ``(U/2.2)**1.3``, U the mean wind
    speed in m/s, over a stated valid range of 0.6-6.7 m/s. The term is
    the same for every particle size, so applying it hourly keeps
    per-size runs additive. ``factors`` holds, for every hour of the file,

    ``q_h = (clip(U_h, u_min, u_max) / u_ref) ** exponent / mean``

    where U_h is the surface file's reference-height wind speed (field
    16) and the mean is over every hour AERMOD models (calms included),
    so the factors average to 1 over them and a constant rate ``Qs``
    times ``q_h`` keeps the period's nominal emission. Hours AERMOD skips
    as missing get ``q_h = 1`` and are left out of the mean: not only a
    missing wind (U >= 90 or U < 0) but any hour metext.f CHKMSG flags,
    such as a missing wind direction, temperature, Monin-Obukhov length,
    mixing height, u* or w*, so ``counts["missing"]`` is the number of
    missing hours AERMOD reports for the file. Calm hours (U = 0, which
    AERMOD never checks for missing data) fall below ``u_min`` and are
    clipped like any other, and counted in ``clipped_low``; AERMOD
    computes no concentration for them.
    The reference height the AP-42 equation assumes for U is not stated
    in the equation; U_h is used at the height the SFC file gives
    (``zref_wind``).
    """

    hours: List[Hour]
    wind_speeds: List[float]
    #: ``(clip(U)/u_ref)**exponent`` before normalization; None for an
    #: hour AERMOD skips as missing. Renormalize these to average over a sub-period.
    raw_factors: List[Optional[float]]
    factors: List[float]
    u_min: float = 0.6
    u_max: float = 6.7
    exponent: float = 1.3
    u_ref: float = 2.2
    source_file: str = ""
    counts: Dict[str, int] = field(default_factory=dict)

    @property
    def raw_mean(self) -> float:
        """Mean of the unnormalized factor over the hours AERMOD models."""
        valid = [r for r in self.raw_factors if r is not None]
        return sum(valid) / len(valid)

    def rates(self, emission_rate: float) -> List[float]:
        """Hourly rates for a source whose period-mean rate is ``emission_rate``."""
        return [emission_rate * f for f in self.factors]

    def summary(self) -> Dict[str, object]:
        """Counts and constants to record beside a run (e.g. in a manifest)."""
        return {
            "source_file": self.source_file,
            "equation": "AP-42 13.2.4 Eq. 1: (U/u_ref)**exponent",
            "u_min": self.u_min, "u_max": self.u_max,
            "exponent": self.exponent, "u_ref": self.u_ref,
            "raw_mean": self.raw_mean,
            **self.counts,
        }


def _read_sfc_hours(path: Path) -> Tuple[List[Hour], List[float], List[bool]]:
    """Date, reference wind speed, and whether AERMOD skips it as a
    missing hour, of every hour of an AERMET .SFC file.

    The fields are those AERMOD's free-format read gives them (metext.f
    METEXT): u* 7, w* 8, convective and mechanical mixing heights 10 and
    11, Monin-Obukhov length 12, wind speed 16, direction 17 and
    temperature 19. Every data line must parse: a skipped line would
    shift every later HOUREMIS record against AERMOD's hours.
    """
    hours: List[Hour] = []
    speeds: List[float] = []
    missing: List[bool] = []
    with open(path) as handle:
        handle.readline()  # header: station, version and options
        for lineno, line in enumerate(handle, start=2):
            if not line.strip():
                continue
            parts = line.split()
            try:
                if len(parts) < 19:
                    raise ValueError(f"{len(parts)} fields")
                hour = (int(parts[0]), int(parts[1]), int(parts[2]), int(parts[4]))
                ustar, wstar, _, ziconv, zimech, obulen = (float(v) for v in parts[6:12])
                speed, wdref, ta = float(parts[15]), float(parts[16]), float(parts[18])
            except ValueError as exc:
                raise ValueError(f"{path}:{lineno}: not an AERMET surface record ({exc})") from exc
            hours.append(hour)
            speeds.append(speed)
            missing.append(_aermod_missing_hour(ustar, wstar, ziconv, zimech,
                                                obulen, speed, wdref, ta))
    return hours, speeds, missing


def ap42_wind_profile(sfc_file: Union[str, Path], *,
                      u_min: float = 0.6, u_max: float = 6.7,
                      exponent: float = 1.3, u_ref: float = 2.2) -> WindEmissionProfile:
    """Build the AP-42 batch-drop wind profile ("profile W") from a .SFC file.

    Parameters
    ----------
    sfc_file : str or Path
        AERMET surface file; every hour of it gets a factor, in file order.
    u_min, u_max : float
        The valid wind range of AP-42 13.2.4 Eq. 1 (m/s); speeds outside
        it are clipped to it and counted.
    exponent, u_ref : float
        The equation's ``(U/2.2)**1.3``.

    Returns
    -------
    WindEmissionProfile
        With ``counts`` of ``hours``, ``valid`` (the hours AERMOD models,
        calms included), ``missing`` (every hour AERMOD skips as missing,
        metext.f CHKMSG, not only a missing wind), ``calm``,
        ``clipped_low`` (calms included) and ``clipped_high``.
    """
    path = Path(sfc_file)
    hours, speeds, missing = _read_sfc_hours(path)
    raw: List[Optional[float]] = []
    counts = {"hours": len(hours), "valid": 0, "missing": 0, "calm": 0,
              "clipped_low": 0, "clipped_high": 0}
    for u, skipped in zip(speeds, missing):
        if skipped:
            counts["missing"] += 1
            raw.append(None)
            continue
        counts["valid"] += 1
        if u == 0.0:
            counts["calm"] += 1
        if u < u_min:
            counts["clipped_low"] += 1
        elif u > u_max:
            counts["clipped_high"] += 1
        raw.append((min(max(u, u_min), u_max) / u_ref) ** exponent)
    if counts["valid"] == 0:
        raise ValueError(f"{path} has no hour AERMOD would not skip as missing")
    valid = [r for r in raw if r is not None]
    mean = sum(valid) / len(valid)
    factors = [1.0 if r is None else r / mean for r in raw]
    return WindEmissionProfile(
        hours=hours, wind_speeds=speeds, raw_factors=raw, factors=factors,
        u_min=u_min, u_max=u_max, exponent=exponent, u_ref=u_ref,
        source_file=str(path), counts=counts,
    )


__all__ = [
    "MISSING_WIND_SPEED",
    "WindEmissionProfile",
    "ap42_wind_profile",
    "hourly_emission_record",
    "write_hourly_emissions",
]

"""
PyAERMOD Meteorological Data QA/QC

Quality assurance checks and diagnostics for processed met data
(SFC / PFL files, or intermediate hourly records). These checks catch
common AERMET output problems that cause silent AERMOD failures:

- Missing-data run lengths (AERMOD tolerates <10% missing; longer gaps
  mean the hour will be skipped, biasing statistics).
- Physical-extreme flags (temperature, wind speed, mixing heights,
  Monin-Obukhov length, friction velocity).
- Stability-class consistency between surface heat-flux sign and
  mixing-height regime (e.g. L<0 should align with CBL, not SBL).
- Low-wind bias screening (high fraction of sub-threshold speeds).
- Temperature-profile monotonicity flags for upper-air soundings.

The functions here operate on plain Python dicts / lists so they can
be applied both to AERMET .SFC output (via `read_surface_file`) and to
raw ingested hourly data (e.g. from `ISDFetcher.read_hourly`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Limits used for extremes screening. Values are intentionally broad: they
# flag *physically implausible* records, not aggressive outliers. Tighten
# only for a specific climate zone.
# ---------------------------------------------------------------------------

AIR_TEMP_LIMITS_C = (-70.0, 60.0)           # Earth-surface plausible range
WIND_SPEED_LIMITS_MS = (0.0, 75.0)          # hurricane-ish cap
MIXING_HEIGHT_LIMITS_M = (10.0, 5000.0)     # AERMOD accepts 1-10000; 10-5000 is sane
USTAR_LIMITS_MS = (0.01, 3.0)               # friction velocity
L_ABS_LIMITS_M = (1.0, 1e6)                 # Monin-Obukhov length (absolute)

LOW_WIND_THRESHOLD_MS = 0.5                  # AERMOD LOWWIND default floor
LOW_WIND_FRACTION_WARN = 0.25                # warn if >25% of hours are calm


@dataclass
class QAQCFinding:
    """One QA/QC issue found in a met record set."""

    level: str          # 'info', 'warning', 'error'
    category: str       # 'missing', 'extreme', 'stability', 'low_wind', 'profile'
    message: str
    # Optional context: hour index or (year, month, day, hour)
    when: Optional[Any] = None
    value: Optional[Any] = None

    def format(self) -> str:
        loc = f" @ {self.when}" if self.when is not None else ""
        val = f" [value={self.value}]" if self.value is not None else ""
        return f"[{self.level.upper()}] {self.category}: {self.message}{loc}{val}"


@dataclass
class QAQCReport:
    """Aggregated QA/QC report for a dataset."""

    findings: List[QAQCFinding] = field(default_factory=list)
    n_records: int = 0
    n_missing: int = 0

    @property
    def n_errors(self) -> int:
        return sum(1 for f in self.findings if f.level == "error")

    @property
    def n_warnings(self) -> int:
        return sum(1 for f in self.findings if f.level == "warning")

    @property
    def missing_fraction(self) -> float:
        return self.n_missing / self.n_records if self.n_records else 0.0

    def by_category(self, category: str) -> List[QAQCFinding]:
        return [f for f in self.findings if f.category == category]

    def extend(self, other: QAQCReport) -> None:
        self.findings.extend(other.findings)
        self.n_records += other.n_records
        self.n_missing += other.n_missing

    def summary(self) -> str:
        return (
            f"{self.n_records} records, {self.n_missing} missing "
            f"({self.missing_fraction:.1%}), "
            f"{self.n_errors} errors, {self.n_warnings} warnings"
        )

    def dump(self, limit: Optional[int] = None) -> str:
        lines = [self.summary(), ""]
        for i, f in enumerate(self.findings):
            if limit is not None and i >= limit:
                lines.append(f"... ({len(self.findings) - limit} more findings)")
                break
            lines.append(f.format())
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Missing-data analysis
# ---------------------------------------------------------------------------

def find_missing_runs(
    records: Sequence[Dict[str, Any]],
    field_name: str,
    min_run: int = 6,
) -> List[tuple]:
    """Return (start_idx, end_idx, length) for runs of missing data.

    A value is "missing" if it is None. Runs shorter than `min_run`
    are ignored (default 6 hours = AERMET Stage 1 'substantive gap').
    """
    runs: List[tuple] = []
    start: Optional[int] = None
    for i, r in enumerate(records):
        is_missing = r.get(field_name) is None
        if is_missing and start is None:
            start = i
        elif not is_missing and start is not None:
            length = i - start
            if length >= min_run:
                runs.append((start, i - 1, length))
            start = None
    if start is not None:
        length = len(records) - start
        if length >= min_run:
            runs.append((start, len(records) - 1, length))
    return runs


def check_missing_data(
    records: Sequence[Dict[str, Any]],
    fields: Iterable[str] = ("wind_speed_ms", "wind_dir", "temp_c"),
    max_missing_fraction: float = 0.10,
    long_run_hours: int = 24,
) -> QAQCReport:
    """Report missing-data issues across a time series.

    Raises *warnings* for long missing runs and an *error* if any field
    exceeds `max_missing_fraction` (default 10% — AERMET guidance).
    """
    rep = QAQCReport(n_records=len(records))
    for field_name in fields:
        n_miss = sum(1 for r in records if r.get(field_name) is None)
        if len(records) > 0:
            frac = n_miss / len(records)
            if frac > max_missing_fraction:
                rep.findings.append(QAQCFinding(
                    level="error",
                    category="missing",
                    message=f"{field_name}: {frac:.1%} missing (>{max_missing_fraction:.0%} limit)",
                    value=frac,
                ))
            elif frac > 0:
                rep.findings.append(QAQCFinding(
                    level="info",
                    category="missing",
                    message=f"{field_name}: {frac:.1%} missing",
                    value=frac,
                ))
        runs = find_missing_runs(records, field_name, min_run=long_run_hours)
        for start, end, length in runs:
            rep.findings.append(QAQCFinding(
                level="warning",
                category="missing",
                message=f"{field_name}: {length}-hour gap from idx {start} to {end}",
                when=(start, end),
                value=length,
            ))
        # Only count primary field (wind_speed) for headline missing fraction
        if field_name == "wind_speed_ms" or rep.n_missing == 0:
            rep.n_missing = max(rep.n_missing, n_miss)
    return rep


# ---------------------------------------------------------------------------
# Physical-extreme screening
# ---------------------------------------------------------------------------

def _check_range(value: Any, lo: float, hi: float) -> Optional[str]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"non-numeric value {value!r}"
    if v < lo:
        return f"{v} below lower limit {lo}"
    if v > hi:
        return f"{v} above upper limit {hi}"
    return None


def check_extremes(records: Sequence[Dict[str, Any]]) -> QAQCReport:
    """Flag records whose values are outside physically plausible ranges."""
    rep = QAQCReport(n_records=len(records))
    field_limits = [
        ("temp_c", AIR_TEMP_LIMITS_C),
        ("wind_speed_ms", WIND_SPEED_LIMITS_MS),
        ("mixing_height_m", MIXING_HEIGHT_LIMITS_M),
        ("ustar", USTAR_LIMITS_MS),
    ]
    for i, r in enumerate(records):
        # Wind direction (0..360 inclusive)
        wd = r.get("wind_dir")
        if wd is not None and (wd < 0 or wd > 360):
            rep.findings.append(QAQCFinding(
                level="error",
                category="extreme",
                message=f"wind_dir out of 0..360: {wd}",
                when=i,
                value=wd,
            ))

        # Monin-Obukhov length: not ranged by sign, just magnitude
        L = r.get("monin_obukhov_m")
        if L is not None:
            absL = abs(float(L))
            if absL < L_ABS_LIMITS_M[0] or absL > L_ABS_LIMITS_M[1]:
                rep.findings.append(QAQCFinding(
                    level="warning",
                    category="extreme",
                    message=f"|Monin-Obukhov length| = {absL} outside {L_ABS_LIMITS_M}",
                    when=i,
                    value=L,
                ))

        for fname, (lo, hi) in field_limits:
            msg = _check_range(r.get(fname), lo, hi)
            if msg:
                rep.findings.append(QAQCFinding(
                    level="error",
                    category="extreme",
                    message=f"{fname}: {msg}",
                    when=i,
                    value=r.get(fname),
                ))
    return rep


# ---------------------------------------------------------------------------
# Stability consistency
# ---------------------------------------------------------------------------

def check_stability_consistency(records: Sequence[Dict[str, Any]]) -> QAQCReport:
    """Flag mismatches between Monin-Obukhov length sign and mixing height.

    In a convective boundary layer (CBL): L < 0 and both `zic` (convective
    mixing height) and `zim` (mechanical mixing height) should be
    populated, with zic > zim typically.

    In a stable boundary layer (SBL): L > 0 and zic should be 0/unused.

    AERMET writes an SFC record with both; inconsistency is a red flag
    that the MMIF or raw obs data were misinterpreted.
    """
    rep = QAQCReport(n_records=len(records))
    for i, r in enumerate(records):
        L = r.get("monin_obukhov_m")
        zic = r.get("convective_mix_height_m", r.get("zic"))
        zim = r.get("mechanical_mix_height_m", r.get("zim"))
        if L is None:
            continue
        try:
            L = float(L)
        except (TypeError, ValueError):
            continue
        if L < 0:  # unstable / CBL
            if zic is not None and zic == 0:
                rep.findings.append(QAQCFinding(
                    level="warning",
                    category="stability",
                    message="CBL regime (L<0) but convective mixing height = 0",
                    when=i,
                ))
            if zic is not None and zim is not None and zic > 0 and zim > zic * 2:
                rep.findings.append(QAQCFinding(
                    level="info",
                    category="stability",
                    message=f"CBL but zim ({zim}) >> zic ({zic}) — unusual",
                    when=i,
                ))
        elif L > 0:  # stable / SBL
            if zic is not None and zic > 0:
                rep.findings.append(QAQCFinding(
                    level="warning",
                    category="stability",
                    message=f"SBL regime (L>0) but zic = {zic} (should be 0)",
                    when=i,
                ))
    return rep


# ---------------------------------------------------------------------------
# Low-wind screening
# ---------------------------------------------------------------------------

def check_low_wind_bias(
    records: Sequence[Dict[str, Any]],
    threshold_ms: float = LOW_WIND_THRESHOLD_MS,
    warn_fraction: float = LOW_WIND_FRACTION_WARN,
) -> QAQCReport:
    """Flag datasets where an unusually high fraction of hours are near-calm.

    An inflated calm fraction is a strong signal of bad anemometer
    placement, poor starting threshold, or incorrect AERMINUTE
    processing. AERMOD has its own LOWWIND options; this is a *data
    quality* alarm, not a runtime config check.
    """
    rep = QAQCReport(n_records=len(records))
    if not records:
        return rep

    n_valid = sum(1 for r in records if r.get("wind_speed_ms") is not None)
    if n_valid == 0:
        rep.findings.append(QAQCFinding(
            level="error",
            category="low_wind",
            message="no valid wind_speed_ms records present",
        ))
        return rep

    n_low = sum(
        1
        for r in records
        if r.get("wind_speed_ms") is not None
        and float(r["wind_speed_ms"]) <= threshold_ms
    )
    frac = n_low / n_valid
    if frac >= warn_fraction:
        rep.findings.append(QAQCFinding(
            level="warning",
            category="low_wind",
            message=(
                f"{frac:.1%} of valid hours at or below {threshold_ms} m/s "
                f"(>{warn_fraction:.0%} triggers LOWWIND concern)"
            ),
            value=frac,
        ))
    return rep


# ---------------------------------------------------------------------------
# Upper-air profile checks
# ---------------------------------------------------------------------------

def check_profile_monotonic(levels: Sequence[Dict[str, Any]]) -> QAQCReport:
    """Flag sounding levels whose pressure is not strictly decreasing.

    Radiosonde ascents must have monotonically decreasing pressure.
    Any reversal is an instrument/QC artifact AERMET Stage 1 will
    either drop or mis-process.
    """
    rep = QAQCReport(n_records=len(levels))
    last_p: Optional[float] = None
    for i, lvl in enumerate(levels):
        p = lvl.get("pressure_pa")
        if p is None:
            continue
        if last_p is not None and p >= last_p:
            rep.findings.append(QAQCFinding(
                level="error",
                category="profile",
                message=f"pressure not decreasing at level {i}: {p} >= {last_p}",
                when=i,
                value=p,
            ))
        last_p = p
    return rep


# ---------------------------------------------------------------------------
# Combined runner
# ---------------------------------------------------------------------------

def run_all_qaqc(records: Sequence[Dict[str, Any]]) -> QAQCReport:
    """Run every surface-data QA/QC check and return a merged report."""
    out = QAQCReport(n_records=len(records))
    out.extend(check_missing_data(records))
    out.extend(check_extremes(records))
    out.extend(check_stability_consistency(records))
    out.extend(check_low_wind_bias(records))
    # `extend` double-counted n_records; fix.
    out.n_records = len(records)
    return out


__all__ = [
    "AIR_TEMP_LIMITS_C",
    "LOW_WIND_FRACTION_WARN",
    "LOW_WIND_THRESHOLD_MS",
    "L_ABS_LIMITS_M",
    "MIXING_HEIGHT_LIMITS_M",
    "USTAR_LIMITS_MS",
    "WIND_SPEED_LIMITS_MS",
    "QAQCFinding",
    "QAQCReport",
    "check_extremes",
    "check_low_wind_bias",
    "check_missing_data",
    "check_profile_monotonic",
    "check_stability_consistency",
    "find_missing_runs",
    "run_all_qaqc",
]

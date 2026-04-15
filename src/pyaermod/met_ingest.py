"""
PyAERMOD Meteorological Data Ingest

Helpers to fetch and preprocess upstream met data before AERMET:

- ASOS1Min: parse 1-minute ASOS DSI-6405 files and aggregate to hourly
  (skeleton of the AERMINUTE algorithm) for use in AERMET Stage 1.
- ISDFetcher: fetch NOAA ISD / ISD-Lite hourly surface observations.
- IGRAFetcher: fetch IGRA v2 upper-air radiosonde soundings.
- MMIFConfig: plug an MMIF-produced .SFC/.PFL pair directly into
  AERMODProject's meteorology pathway (bypassing AERMET).

All network helpers accept either a local path or a URL; they are
designed to be mockable in tests.
"""

from __future__ import annotations

import gzip
import io
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ._optional import optional_import, require

requests = optional_import("requests")
HAS_REQUESTS = requests is not None


def _require_requests() -> None:
    require(requests, "requests", pip_extra="met")


# ---------------------------------------------------------------------------
# ASOS 1-minute data (AERMINUTE equivalent, skeleton)
# ---------------------------------------------------------------------------

# ASOS 1-min data columns per NOAA DSI-6405 documentation (subset).
# We only parse the fields AERMINUTE uses: station, timestamp, wind direction,
# wind speed, wind character (peak/gust), and QC flags.
_ASOS_1MIN_LINE = re.compile(
    r"^(?P<wban>\d{5})\s+"
    r"(?P<call>\w{3,4})\s+"
    r"(?P<ts>\d{8}\s+\d{4})\s+"
    r".*?"
    r"(?P<wd>\d{3})\s+"
    r"(?P<ws>\d{1,3})\s*KT"
)


@dataclass
class ASOS1MinRecord:
    """One parsed 1-minute ASOS observation."""
    wban: str
    call_sign: str
    year: int
    month: int
    day: int
    hour: int
    minute: int
    wind_dir_deg: Optional[float]  # 0-360, 0 = calm
    wind_speed_ms: Optional[float]  # knots converted to m/s
    is_calm: bool = False
    is_variable: bool = False


def parse_asos_1min_line(line: str) -> Optional[ASOS1MinRecord]:
    """Parse a single 1-minute ASOS DSI-6405 page-1 line.

    Returns None if the line is not parseable. Real DSI-6405 has a
    complex fixed-width format; this covers the common subset used
    by AERMINUTE (wind speed + direction with QC flag). Knots are
    converted to m/s.
    """
    # DSI-6405 page 1 has varying whitespace; use a tolerant regex.
    m = _ASOS_1MIN_LINE.match(line)
    if not m:
        return None

    try:
        ts = m.group("ts").replace(" ", "")  # YYYYMMDDHHMM
        year = int(ts[0:4])
        month = int(ts[4:6])
        day = int(ts[6:8])
        hour = int(ts[8:10])
        minute = int(ts[10:12])
        wd = int(m.group("wd"))
        ws_kt = int(m.group("ws"))
    except (ValueError, IndexError):
        return None

    # Calm: WD=000 and WS=00
    is_calm = wd == 0 and ws_kt == 0
    # Variable: WD=990 per ASOS convention
    is_variable = wd == 990

    wind_dir = None if is_calm or is_variable else float(wd)
    wind_speed = None if is_calm else ws_kt * 0.51444  # knots -> m/s

    return ASOS1MinRecord(
        wban=m.group("wban"),
        call_sign=m.group("call"),
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        wind_dir_deg=wind_dir,
        wind_speed_ms=wind_speed,
        is_calm=is_calm,
        is_variable=is_variable,
    )


def aggregate_1min_to_hourly(records: List[ASOS1MinRecord]) -> List[Dict[str, Any]]:
    """Aggregate 1-minute observations to hourly vector averages.

    This is the core AERMINUTE algorithm (simplified):
    - Group by (year, month, day, hour)
    - Compute vector-mean wind (u, v) for non-calm, non-variable records
    - Calm hour if all records in that hour are calm
    - Variable hour if valid records < threshold (AERMINUTE uses 2)

    Returns a list of dicts with keys year/month/day/hour/ws/wd/n_obs/flag.
    """
    buckets: Dict[Tuple[int, int, int, int], List[ASOS1MinRecord]] = {}
    for r in records:
        key = (r.year, r.month, r.day, r.hour)
        buckets.setdefault(key, []).append(r)

    out: List[Dict[str, Any]] = []
    for (y, mo, d, h), recs in sorted(buckets.items()):
        valid = [r for r in recs if not r.is_calm and not r.is_variable
                 and r.wind_dir_deg is not None and r.wind_speed_ms is not None]
        n = len(valid)
        if n == 0:
            # All calm or all variable
            flag = "CALM" if all(r.is_calm for r in recs) else "VAR"
            out.append({
                "year": y, "month": mo, "day": d, "hour": h,
                "ws": 0.0, "wd": 0.0, "n_obs": len(recs), "flag": flag,
            })
            continue
        if n < 2:  # AERMINUTE minimum-obs threshold
            out.append({
                "year": y, "month": mo, "day": d, "hour": h,
                "ws": 0.0, "wd": 0.0, "n_obs": n, "flag": "INSUF",
            })
            continue

        u_sum = 0.0
        v_sum = 0.0
        for r in valid:
            theta = math.radians(270.0 - r.wind_dir_deg)  # met -> math
            u_sum += r.wind_speed_ms * math.cos(theta)
            v_sum += r.wind_speed_ms * math.sin(theta)
        u = u_sum / n
        v = v_sum / n
        ws = math.hypot(u, v)
        wd = (270.0 - math.degrees(math.atan2(v, u))) % 360.0
        out.append({
            "year": y, "month": mo, "day": d, "hour": h,
            "ws": round(ws, 3), "wd": round(wd, 1),
            "n_obs": n, "flag": "OK",
        })
    return out


def parse_asos_1min_file(path: Union[str, Path]) -> List[ASOS1MinRecord]:
    """Parse a DSI-6405 1-minute ASOS file into records.

    Handles .gz compression transparently.
    """
    path = Path(path)
    opener = gzip.open if str(path).endswith(".gz") else open
    records: List[ASOS1MinRecord] = []
    with opener(path, "rt", encoding="latin-1", errors="replace") as f:
        for line in f:
            rec = parse_asos_1min_line(line)
            if rec is not None:
                records.append(rec)
    return records


# ---------------------------------------------------------------------------
# NOAA ISD / ISD-Lite hourly surface observations
# ---------------------------------------------------------------------------

ISD_LITE_URL = (
    "https://www.ncei.noaa.gov/pub/data/noaa/isd-lite/{year}/{usaf}-{wban}-{year}.gz"
)
ISD_FULL_URL = (
    "https://www.ncei.noaa.gov/pub/data/noaa/{year}/{usaf}-{wban}-{year}.gz"
)


@dataclass
class ISDStationId:
    """USAF + WBAN identifier for an ISD station."""
    usaf: str  # 6 digits
    wban: str  # 5 digits

    def __post_init__(self) -> None:
        if not (len(self.usaf) == 6 and self.usaf.isdigit()):
            raise ValueError(f"USAF must be 6 digits, got {self.usaf!r}")
        if not (len(self.wban) == 5 and self.wban.isdigit()):
            raise ValueError(f"WBAN must be 5 digits, got {self.wban!r}")


class ISDFetcher:
    """Fetch NOAA ISD / ISD-Lite surface observations.

    ISD-Lite is the simpler hourly product (8 elements). Use `use_lite=True`
    unless you need the full ISD record for AERMET's ISHD reader.
    """

    def __init__(self, cache_dir: Optional[Union[str, Path]] = None, use_lite: bool = True) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.use_lite = use_lite
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(self, station: ISDStationId, year: int) -> bytes:
        """Download the ISD file for one station-year; returns raw gzipped bytes.

        If `cache_dir` was set and the file is already cached, returns the
        cached bytes without hitting the network.
        """
        _require_requests()
        fname = f"{station.usaf}-{station.wban}-{year}.gz"
        cache_path: Optional[Path] = None
        if self.cache_dir:
            cache_path = self.cache_dir / fname
            if cache_path.exists():
                return cache_path.read_bytes()

        url = (ISD_LITE_URL if self.use_lite else ISD_FULL_URL).format(
            year=year, usaf=station.usaf, wban=station.wban
        )
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.content
        if cache_path is not None:
            cache_path.write_bytes(data)
        return data

    def read_hourly(self, station: ISDStationId, year: int) -> List[Dict[str, Any]]:
        """Fetch ISD-Lite and parse into list of hourly dicts.

        ISD-Lite columns (whitespace-delimited, -9999 = missing):
        YEAR MONTH DAY HOUR T DEWPT SLP WDIR WSPD SKY_COND 1HR_PRCP 6HR_PRCP
        T/DEWPT in tenths of C; WSPD in tenths of m/s; SLP in tenths of hPa.
        """
        if not self.use_lite:
            raise NotImplementedError(
                "read_hourly currently parses ISD-Lite only. "
                "Set use_lite=True or parse the full ISD bytes manually."
            )
        raw = self.fetch(station, year)
        text = gzip.decompress(raw).decode("latin-1", errors="replace")
        out: List[Dict[str, Any]] = []
        for line in text.splitlines():
            parts = line.split()
            if len(parts) < 8:
                continue
            try:
                y, mo, d, h = (int(x) for x in parts[:4])
                t = int(parts[4])
                td = int(parts[5])
                wdir = int(parts[7])
                wspd = int(parts[8])
            except ValueError:
                continue
            out.append({
                "year": y, "month": mo, "day": d, "hour": h,
                "temp_c": None if t == -9999 else t / 10.0,
                "dewpt_c": None if td == -9999 else td / 10.0,
                "wind_dir": None if wdir == -9999 else float(wdir),
                "wind_speed_ms": None if wspd == -9999 else wspd / 10.0,
            })
        return out


# ---------------------------------------------------------------------------
# IGRA v2 upper-air soundings
# ---------------------------------------------------------------------------

IGRA_V2_URL = (
    "https://www.ncei.noaa.gov/pub/data/igra/data/data-y2d/{station_id}-data.txt.zip"
)


@dataclass
class IGRASounding:
    """One radiosonde ascent."""
    station_id: str
    year: int
    month: int
    day: int
    hour: int
    num_levels: int
    levels: List[Dict[str, Any]] = field(default_factory=list)


def parse_igra_v2(text: str) -> List[IGRASounding]:
    """Parse IGRA v2 data-format text into a list of soundings.

    Header line format: "#USM00072469 2020 01 01 00 2359 ..." etc.
    Level lines follow; count is given in the header. We extract just
    enough to be useful for AERMET Stage 1 input (pressure, height,
    temp, wind).
    """
    soundings: List[IGRASounding] = []
    current: Optional[IGRASounding] = None
    levels_remaining = 0
    for raw in text.splitlines():
        if raw.startswith("#"):
            # Header
            parts = raw.split()
            if len(parts) < 7:
                continue
            try:
                station = parts[0][1:]  # strip leading '#'
                year = int(parts[1])
                month = int(parts[2])
                day = int(parts[3])
                hour = int(parts[4])
                nlev = int(parts[6])
            except (ValueError, IndexError):
                continue
            current = IGRASounding(
                station_id=station, year=year, month=month,
                day=day, hour=hour, num_levels=nlev,
            )
            soundings.append(current)
            levels_remaining = nlev
        else:
            if current is None or levels_remaining <= 0:
                continue
            # Level line (tokenized):
            # LVLTYP1 LVLTYP2 ETIME PRESS[flag] GPH[flag] TEMP[flag] RH DPDP WDIR WSPD
            # The [flag] characters are letters appended to the numeric value
            # with no space, so strip trailing non-digit characters.
            toks = raw.split()
            if len(toks) < 10:
                levels_remaining -= 1
                continue

            def _int_or_none(s: str) -> Optional[int]:
                # Strip trailing letter flags (A/B/etc.) that IGRA appends
                s = re.sub(r"[A-Za-z]+$", "", s)
                try:
                    v = int(s)
                except ValueError:
                    return None
                return None if v == -9999 else v

            try:
                press = _int_or_none(toks[3])
                gph = _int_or_none(toks[4])
                temp = _int_or_none(toks[5])
                wdir = _int_or_none(toks[8])
                wspd = _int_or_none(toks[9])
            except IndexError:
                levels_remaining -= 1
                continue
            current.levels.append({
                "pressure_pa": None if press == -9999 else press,
                "height_m": None if gph == -9999 else gph,
                "temp_c": None if temp == -9999 else temp / 10.0,
                "wind_dir": None if wdir == -9999 else float(wdir),
                "wind_speed_ms": None if wspd == -9999 else wspd / 10.0,
            })
            levels_remaining -= 1
    return soundings


class IGRAFetcher:
    """Fetch IGRA v2 upper-air soundings for a station."""

    def __init__(self, cache_dir: Optional[Union[str, Path]] = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_text(self, station_id: str) -> str:
        """Return the raw IGRA v2 text (year-to-date) for a station id.

        station_id is the 11-character IGRA id (e.g. 'USM00072469').
        """
        _require_requests()
        fname = f"{station_id}-data.txt"
        cache_path: Optional[Path] = None
        if self.cache_dir:
            cache_path = self.cache_dir / fname
            if cache_path.exists():
                return cache_path.read_text(encoding="latin-1")

        url = IGRA_V2_URL.format(station_id=station_id)
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()

        import zipfile
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            member = next((n for n in zf.namelist() if n.endswith(".txt")), None)
            if member is None:
                raise ValueError(f"IGRA zip for {station_id} contained no .txt member")
            text = zf.read(member).decode("latin-1", errors="replace")

        if cache_path is not None:
            cache_path.write_text(text, encoding="latin-1")
        return text

    def read_soundings(self, station_id: str) -> List[IGRASounding]:
        return parse_igra_v2(self.fetch_text(station_id))


# ---------------------------------------------------------------------------
# MMIF (Mesoscale Model Interface) passthrough
# ---------------------------------------------------------------------------

@dataclass
class MMIFConfig:
    """Describes an MMIF-produced meteorology pair.

    MMIF (EPA's prognostic-to-AERMOD bridge) emits AERMOD-compatible .SFC
    and .PFL files from WRF/MM5/RAMS output. Since AERMOD reads these
    directly, the `MMIFConfig` just provides a sanity-checked plug into
    `MeteorologyPathway`.
    """
    surface_file: str
    profile_file: str
    surface_station_id: str = "MMIF"
    upper_air_station_id: str = "MMIF"

    def __post_init__(self) -> None:
        for attr in ("surface_file", "profile_file"):
            val = getattr(self, attr)
            if not val or not isinstance(val, str):
                raise ValueError(f"MMIFConfig.{attr} must be a non-empty string")

    def to_meteorology(self) -> Dict[str, str]:
        """Return kwargs suitable for MeteorologyPathway(...).

        Use as: MeteorologyPathway(**mmif_config.to_meteorology(), ...).
        """
        return {
            "surface_file": self.surface_file,
            "profile_file": self.profile_file,
            "surface_station_id": self.surface_station_id,
            "upper_air_station_id": self.upper_air_station_id,
        }


__all__ = [
    "ASOS1MinRecord",
    "parse_asos_1min_line",
    "parse_asos_1min_file",
    "aggregate_1min_to_hourly",
    "ISDStationId",
    "ISDFetcher",
    "IGRASounding",
    "parse_igra_v2",
    "IGRAFetcher",
    "MMIFConfig",
]

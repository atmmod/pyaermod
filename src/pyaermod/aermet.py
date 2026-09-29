"""
PyAERMOD AERMET Input Generator and Output Parser

Generates AERMET input files for meteorological data preprocessing and
parses AERMET output files (.SFC surface and .PFL profile).

AERMET is the EPA's meteorological preprocessor for AERMOD.

Processing stages:
1. Stage 1: Extract and QA/QC observational data
2. Stage 2: Merge surface and upper air data
3. Stage 3: Calculate boundary layer parameters
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Union

import pandas as pd


@dataclass
class AERMETStation:
    """Surface meteorological station information"""
    station_id: str
    station_name: str
    latitude: float  # decimal degrees
    longitude: float  # decimal degrees
    time_zone: int  # UTC offset (e.g., -5 for EST)

    # Optional parameters
    elevation: Optional[float] = None  # meters
    anemometer_height: float = 10.0  # meters

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"latitude must be between -90 and 90, got {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"longitude must be between -180 and 180, got {self.longitude}")
        if self.anemometer_height <= 0:
            raise ValueError(f"anemometer_height must be > 0, got {self.anemometer_height}")


@dataclass
class UpperAirStation:
    """Upper air (radiosonde) station information"""
    station_id: str
    station_name: str
    latitude: float
    longitude: float

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"latitude must be between -90 and 90, got {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"longitude must be between -180 and 180, got {self.longitude}")


@dataclass
class AERMETStage1:
    """
    AERMET Stage 1: Extract and QA/QC observational data

    Reads raw meteorological data and performs quality assurance.
    """

    # Job control
    job_id: str = "STAGE1"
    messages: int = 2  # Message level (1=few, 2=normal, 3=verbose)

    # Surface data
    surface_station: Optional[AERMETStation] = None
    surface_data_file: Optional[str] = None
    surface_format: str = "ISHD"  # or "HUSWO", "SCRAM", "SAMSON"

    # Upper air data
    upper_air_station: Optional[UpperAirStation] = None
    upper_air_data_file: Optional[str] = None

    # Date range
    start_date: str = "2020/01/01"  # YYYY/MM/DD
    end_date: str = "2020/12/31"

    # Output
    output_file: str = "stage1.out"
    extract_file: str = "stage1.ext"
    qa_file: str = "stage1.qa"

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 1 input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 1 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # UPPERAIR pathway
        if self.upper_air_station and self.upper_air_data_file:
            lines.append("UPPERAIR")
            lines.append(f"   DATA       {self.upper_air_data_file} FSL")
            lines.append(f"   EXTRACT    {self.extract_file.replace('.ext', '_ua.ext')}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
            lines.append("")

        # SURFACE pathway
        if self.surface_station and self.surface_data_file:
            lines.append("SURFACE")
            lines.append(f"   DATA       {self.surface_data_file} {self.surface_format}")
            lines.append(f"   EXTRACT    {self.extract_file}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")

            # Station parameters
            if self.surface_station.anemometer_height is not None:
                lines.append(f"   ANEMHGT    {self.surface_station.anemometer_height:.1f}")

            lines.append(f"   LOCATION   {self.surface_station.station_id} " +
                        f"{self.surface_station.latitude:.4f} " +
                        f"{self.surface_station.longitude:.4f} {self.surface_station.time_zone}")

            if self.surface_station.elevation is not None:
                lines.append(f"   ELEVATION  {self.surface_station.elevation:.1f}")

            lines.append("")

        # QA pathway
        if self.surface_station and self.surface_data_file:
            lines.append("QA")
            lines.append(f"   EXTRACT    {self.qa_file}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class AERMETStage2:
    """
    AERMET Stage 2: Merge surface and upper air data

    Combines Stage 1 outputs into merged file.
    """

    # Job control
    job_id: str = "STAGE2"
    messages: int = 2

    # Input files from Stage 1
    surface_extract: str = "stage1.ext"
    upper_air_extract: Optional[str] = None

    # Date range
    start_date: str = "2020/01/01"
    end_date: str = "2020/12/31"

    # Output
    output_file: str = "stage2.out"
    merge_file: str = "stage2.mrg"

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 2 input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 2 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # UPPERAIR pathway
        if self.upper_air_extract:
            lines.append("UPPERAIR")
            lines.append(f"   INPUT      {self.upper_air_extract}")
            lines.append("")

        # SURFACE pathway
        lines.append("SURFACE")
        lines.append(f"   INPUT      {self.surface_extract}")
        lines.append("")

        # MERGE pathway
        lines.append("MERGE")
        lines.append(f"   OUTPUT     {self.merge_file}")
        lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
        lines.append("")

        return "\n".join(lines)


@dataclass
class AERMETStage3:
    """
    AERMET Stage 3: Calculate boundary layer parameters

    Produces final AERMOD-ready meteorology files (.sfc and .pfl).
    """

    # Job control
    job_id: str = "STAGE3"
    messages: int = 2

    # Input from Stage 2
    merge_file: str = "stage2.mrg"

    # Site characteristics
    station: Optional[AERMETStation] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    time_zone: Optional[int] = None

    # Surface characteristics
    num_sectors: int = 1  # Number of wind direction sectors for surface characteristics
    site_char: List[str] = field(default_factory=list)  # Monthly surface characteristics

    # Albedo, Bowen ratio, roughness length (12 months)
    albedo: List[float] = field(default_factory=lambda: [0.15] * 12)
    bowen: List[float] = field(default_factory=lambda: [1.0] * 12)
    roughness: List[float] = field(default_factory=lambda: [0.1] * 12)

    # Date range
    start_date: str = "2020/01/01"
    end_date: str = "2020/12/31"

    # Output files
    output_file: str = "stage3.out"
    surface_file: str = "aermod.sfc"
    profile_file: str = "aermod.pfl"

    def __post_init__(self):
        # Validate partial location parameters (when station is not provided)
        if self.station is None:
            loc_params = [self.latitude, self.longitude, self.time_zone]
            provided = [p is not None for p in loc_params]
            if any(provided) and not all(provided):
                raise ValueError(
                    "latitude, longitude, and time_zone must all be provided or all be None"
                )

        # Validate array lengths
        if len(self.albedo) != 12:
            raise ValueError(f"albedo must have exactly 12 elements, got {len(self.albedo)}")
        if len(self.bowen) != 12:
            raise ValueError(f"bowen must have exactly 12 elements, got {len(self.bowen)}")
        if len(self.roughness) != 12:
            raise ValueError(f"roughness must have exactly 12 elements, got {len(self.roughness)}")

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 3 input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 3 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # METPREP pathway — Stage 3 reads merged data and produces .sfc/.pfl
        lines.append("METPREP")
        lines.append(f"   DATA       {self.merge_file}")
        lines.append(f"   OUTPUT     {self.surface_file}")
        lines.append(f"   PROFILE    {self.profile_file}")
        lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")

        # Location
        if self.station:
            lines.append(f"   LOCATION   {self.station.station_id} " +
                        f"{self.station.latitude:.4f} " +
                        f"{self.station.longitude:.4f} {self.station.time_zone}")
        elif self.latitude is not None and self.longitude is not None and self.time_zone is not None:
            lines.append(f"   LOCATION   SITE {self.latitude:.4f} " +
                        f"{self.longitude:.4f} {self.time_zone}")

        # Surface characteristics — FREQ_SECT ANNUAL n_sectors
        lines.append(f"   FREQ_SECT  ANNUAL  {self.num_sectors}")

        # Monthly parameters (Albedo, Bowen, Roughness)
        if len(self.albedo) == 12:
            albedo_str = " ".join(f"{a:.2f}" for a in self.albedo)
            lines.append(f"   ALBEDO     {albedo_str}")

        if len(self.bowen) == 12:
            bowen_str = " ".join(f"{b:.2f}" for b in self.bowen)
            lines.append(f"   BOWEN      {bowen_str}")

        if len(self.roughness) == 12:
            rough_str = " ".join(f"{r:.3f}" for r in self.roughness)
            lines.append(f"   ROUGHNESS  {rough_str}")

        lines.append("")

        return "\n".join(lines)


def write_aermet_runfile(stage: int, input_file: str, output_path: str = "."):
    """
    Create a simple AERMET run script

    Args:
        stage: AERMET stage (1, 2, or 3)
        input_file: Path to input file
        output_path: Directory for outputs
    """
    script = f"""#!/bin/bash
# AERMET Stage {stage} Run Script

# Set paths
AERMET_EXE="aermet"
INPUT_FILE="{input_file}"
OUTPUT_PATH="{output_path}"

# Create output directory
mkdir -p $OUTPUT_PATH

# Run AERMET
cd $OUTPUT_PATH
$AERMET_EXE < ../$INPUT_FILE

echo "AERMET Stage {stage} complete"
"""

    script_file = f"run_aermet_stage{stage}.sh"
    with open(script_file, 'w') as f:
        f.write(script)

    # Make executable
    import os
    os.chmod(script_file, 0o755)

    return script_file


# ============================================================================
# AERMET OUTPUT FILE PARSERS (.SFC and .PFL)
# ============================================================================


@dataclass
class SurfaceFileHeader:
    """Parsed header from an AERMET .SFC surface file."""

    latitude: float = 0.0
    longitude: float = 0.0
    ua_id: str = ""
    sf_id: str = ""
    os_id: str = ""
    version: str = ""
    options: str = ""


# .SFC column names based on AERMET v26135 Fortran FORMAT statements (same
# layout as v24142; v26135 writes four-digit years, which parse identically).
# The exact set of columns varies slightly by version, but this covers
# the standard output.
SFC_COLUMNS = [
    "year", "month", "day", "jday", "hour",
    "H",             # Sensible heat flux (W/m^2)
    "ustar",         # Friction velocity (m/s)
    "wstar",         # Convective velocity scale (m/s)
    "VPTG",          # Potential temperature gradient above PBL (K/m)
    "Zic",           # Convective mixing height (m)
    "Zim",           # Mechanical mixing height (m)
    "L",             # Monin-Obukhov length (m)
    "z0",            # Surface roughness length (m)
    "BOWEN",         # Bowen ratio
    "ALBEDO",        # Albedo
    "wind_speed",    # Reference wind speed (m/s)
    "wind_dir",      # Reference wind direction (degrees)
    "zref_wind",     # Reference height for wind (m)
    "temp",          # Ambient temperature (K)
    "zref_temp",     # Reference height for temperature (m)
    "ipcode",        # Precipitation code
    "pamt",          # Precipitation amount (mm)
    "rh",            # Relative humidity (%)
    "pres",          # Station pressure (mb)
    "ccvr",          # Cloud cover (tenths)
    "method",        # Method flag
    "subs",          # Substitution flag
]


def parse_sfc_header(header_line: str) -> SurfaceFileHeader:
    """
    Parse the header line of an AERMET .SFC file.

    Parameters
    ----------
    header_line : str
        First line of the .SFC file.

    Returns
    -------
    SurfaceFileHeader
        Parsed header metadata.
    """
    hdr = SurfaceFileHeader()

    # Latitude: e.g. "42.750N" or "41.300S"
    lat_match = re.search(r"([\d.]+)([NS])", header_line)
    if lat_match:
        hdr.latitude = float(lat_match.group(1))
        if lat_match.group(2) == "S":
            hdr.latitude = -hdr.latitude

    # Longitude: e.g. "73.800W" or "158.042E"
    lon_match = re.search(r"([\d.]+)([EW])", header_line)
    if lon_match:
        hdr.longitude = float(lon_match.group(1))
        if lon_match.group(2) == "W":
            hdr.longitude = -hdr.longitude

    # Station IDs — use lookahead to stop before the next keyword
    ua_match = re.search(r"UA_ID:\s*(.*?)(?=\s+SF_ID:)", header_line)
    if ua_match:
        hdr.ua_id = ua_match.group(1).strip()
    sf_match = re.search(r"SF_ID:\s*(.*?)(?=\s+OS_ID:)", header_line)
    if sf_match:
        hdr.sf_id = sf_match.group(1).strip()
    os_match = re.search(r"OS_ID:\s*(.*?)(?=\s+VERSION:)", header_line)
    if os_match:
        hdr.os_id = os_match.group(1).strip()

    # Version
    ver_match = re.search(r"VERSION:\s*(\S+)", header_line)
    if ver_match:
        hdr.version = ver_match.group(1).strip()

    # Everything after VERSION field = options
    opts_match = re.search(r"VERSION:\s*\S+\s+(.*)", header_line)
    if opts_match:
        hdr.options = opts_match.group(1).strip()

    return hdr


def read_surface_file(filepath: Union[str, Path]) -> Dict:
    """
    Parse an AERMET .SFC surface meteorology file.

    Parameters
    ----------
    filepath : str or Path
        Path to the .SFC file.

    Returns
    -------
    dict
        Dictionary with keys:
        - ``"header"``: :class:`SurfaceFileHeader`
        - ``"data"``: :class:`pandas.DataFrame` with hourly surface parameters
    """
    filepath = Path(filepath)
    with open(filepath) as f:
        header_line = f.readline()
        data_lines = f.readlines()

    header = parse_sfc_header(header_line)

    rows = []
    for line in data_lines:
        parts = line.split()
        if len(parts) < 20:
            continue
        try:
            row = {
                "year": int(parts[0]),
                "month": int(parts[1]),
                "day": int(parts[2]),
                "jday": int(parts[3]),
                "hour": int(parts[4]),
                "H": float(parts[5]),
                "ustar": float(parts[6]),
                "wstar": float(parts[7]),
                "VPTG": float(parts[8]),
                "Zic": float(parts[9]),
                "Zim": float(parts[10]),
                "L": float(parts[11]),
                "z0": float(parts[12]),
                "BOWEN": float(parts[13]),
                "ALBEDO": float(parts[14]),
                "wind_speed": float(parts[15]),
                "wind_dir": float(parts[16]),
                "zref_wind": float(parts[17]),
                "temp": float(parts[18]),
                "zref_temp": float(parts[19]),
            }
            # Optional trailing columns (may be absent in older versions)
            if len(parts) > 20:
                row["ipcode"] = int(parts[20])
            if len(parts) > 21:
                row["pamt"] = float(parts[21])
            if len(parts) > 22:
                row["rh"] = float(parts[22])
            if len(parts) > 23:
                row["pres"] = float(parts[23])
            if len(parts) > 24:
                row["ccvr"] = int(parts[24])
            if len(parts) > 25:
                row["method"] = parts[25]
            if len(parts) > 26:
                row["subs"] = parts[26]
            rows.append(row)
        except (ValueError, IndexError):
            continue

    df = pd.DataFrame(rows)
    return {"header": header, "data": df}


@dataclass
class ProfileFileHeader:
    """Metadata for a .PFL file (no header line — metadata inferred from data)."""

    num_hours: int = 0
    num_levels: int = 0
    heights: List[float] = field(default_factory=list)


PFL_COLUMNS = [
    "year", "month", "day", "hour",
    "height",        # Measurement height (m AGL)
    "top_flag",      # Top of profile flag (0 or 1)
    "wind_dir",      # Wind direction (degrees)
    "wind_speed",    # Wind speed (m/s)
    "temp_diff",     # Temperature difference (K) or ambient temp
    "sigma_theta",   # Standard deviation of wind direction (degrees)
    "sigma_w",       # Standard deviation of vertical wind speed (m/s)
]


def read_profile_file(filepath: Union[str, Path]) -> Dict:
    """
    Parse an AERMET .PFL profile meteorology file.

    Parameters
    ----------
    filepath : str or Path
        Path to the .PFL file.

    Returns
    -------
    dict
        Dictionary with keys:
        - ``"header"``: :class:`ProfileFileHeader` with summary metadata
        - ``"data"``: :class:`pandas.DataFrame` with profile observations
    """
    filepath = Path(filepath)
    rows = []
    with open(filepath) as f:
        for line in f:
            parts = line.split()
            if len(parts) < 9:
                continue
            try:
                row = {
                    "year": int(parts[0]),
                    "month": int(parts[1]),
                    "day": int(parts[2]),
                    "hour": int(parts[3]),
                    "height": float(parts[4]),
                    "top_flag": int(parts[5]),
                    "wind_dir": float(parts[6]),
                    "wind_speed": float(parts[7]),
                    "temp_diff": float(parts[8]),
                }
                if len(parts) > 9:
                    row["sigma_theta"] = float(parts[9])
                if len(parts) > 10:
                    row["sigma_w"] = float(parts[10])
                rows.append(row)
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(rows)

    header = ProfileFileHeader()
    if not df.empty:
        header.num_hours = df.groupby(["year", "month", "day", "hour"]).ngroups
        header.heights = sorted(df["height"].unique().tolist())
        header.num_levels = len(header.heights)

    return {"header": header, "data": df}


# ============================================================================
# THE PERIOD A SURFACE FILE COVERS
# ============================================================================
#
# AERMOD counts the years of met data it has processed (NUMYRS) in
# CHK_ENDYR (aermod.f): a year ends at the hour before the first hour of
# data, one year on. MESET/METEXT (meset.f, metext.f) set that hour from
# the first hour read (IENDMN, IENDDY, IENDHOUR: hour 1 of 1 March gives
# hour 24 of the last day of February, taken as 29 and read as 28 in a
# year that is not a leap year). ANNUAL averages divide by NUMYRS, and a
# run that ends with NUMYRS = 0 stops with fatal error E480 ("Less than
# 1yr for MULTYEAR, MAXDCONT or ANNUAL Ave") after processing every hour.
# Two-digit years are windowed as AERMOD does: 50-99 are 19xx, 00-49 20xx.

_DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)   # IDYMAX


def _is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def _four_digit_year(year: int) -> int:
    if year >= 100:
        return year
    return 1900 + year if year >= 50 else 2000 + year


@dataclass(frozen=True)
class SurfaceFilePeriod:
    """The hours of met data an AERMET ``.SFC`` file holds.

    Read by :func:`read_surface_period`. Times are the start of the first
    hour and the end of the last one, so a file of the 96 hours of 1 to 4
    March 1988 has ``first = 1988-03-01 00:00`` and ``last = 1988-03-05
    00:00``. AERMET's hour 24 is the hour that ends at midnight.

    Attributes
    ----------
    first, last
        The start of the first hour and the end of the last hour of data.
    hours
        The number of hourly records in the file.
    days
        The number of distinct days with at least one hour of data; AERMOD
        prints one "Now Processing Data For Day No." line for each.
    surface_station, upper_air_station
        The station IDs from the file's header (``SF_ID``, ``UA_ID``).
    """

    first: datetime
    last: datetime
    hours: int
    days: int
    surface_station: str = ""
    upper_air_station: str = ""

    @property
    def first_year(self) -> int:
        return self.first.year

    @property
    def first_day(self) -> date:
        return self.first.date()

    @property
    def last_day(self) -> date:
        """The day of the last hour (not the midnight that ends it)."""
        return (self.last - timedelta(hours=1)).date()

    @property
    def complete_years(self) -> int:
        """How many years of data AERMOD counts in a run over the whole file.

        This is AERMOD's ``NUMYRS`` at the end of such a run: the number of
        times the data reach the end of a year, which is the hour before the
        first hour, one year on (see the comment above this class). ANNUAL
        averages need at least one; with none AERMOD stops with E480.
        Assumes the hours between the first and the last are all present,
        as AERMET writes them.
        """
        start_hour = self.first.hour + 1           # AERMET's hour 1..24
        if start_hour > 1:
            end_month, end_day, end_hour = self.first.month, self.first.day, start_hour - 1
        else:
            end_hour = 24
            if self.first.day > 1:
                end_month, end_day = self.first.month, self.first.day - 1
            else:
                end_month = self.first.month - 1 or 12
                end_day = _DAYS_IN_MONTH[end_month - 1]
        count = 0
        for year in range(self.first.year, self.last.year + 1):
            day = end_day
            if end_month == 2 and end_day == 29 and not _is_leap(year):
                day = 28
            year_end = datetime(year, end_month, day) + timedelta(hours=end_hour)
            if self.first < year_end <= self.last:
                count += 1
        return count

    def describe(self) -> str:
        """``"1988-03-01 to 1988-03-04 (4 days, 96 hours)"``."""
        days = f"{self.days} day{'s' if self.days != 1 else ''}"
        hours = f"{self.hours} hour{'s' if self.hours != 1 else ''}"
        return f"{self.first_day.isoformat()} to {self.last_day.isoformat()} ({days}, {hours})"


def read_surface_period(filepath: Union[str, Path]) -> SurfaceFilePeriod:
    """Read which hours of met data an AERMET ``.SFC`` file holds.

    Reads the header's station IDs and the date and hour of every data
    record, without loading the data into a DataFrame, so it is quick
    even for a five-year file.

    Parameters
    ----------
    filepath : str or Path
        Path to the ``.SFC`` file.

    Returns
    -------
    SurfaceFilePeriod

    Raises
    ------
    OSError
        If the file cannot be read.
    ValueError
        If the file holds no data record (a line starting with year,
        month, day, Julian day and hour).
    """
    filepath = Path(filepath)
    first: Optional[datetime] = None
    last: Optional[datetime] = None
    hours = 0
    days = set()
    with open(filepath, encoding="latin-1") as f:
        header = parse_sfc_header(f.readline())
        for line in f:
            parts = line.split(None, 5)
            if len(parts) < 5:
                continue
            try:
                year, month, day, _jday, hour = (int(p) for p in parts[:5])
                start = datetime(_four_digit_year(year), month, day) + timedelta(hours=hour - 1)
            except ValueError:
                continue
            if not 1 <= hour <= 24:
                continue
            hours += 1
            days.add(start.date())
            if first is None or start < first:
                first = start
            if last is None or start > last:
                last = start
    if first is None or last is None:
        raise ValueError(f"{filepath.name}: no hourly records in the surface file")
    return SurfaceFilePeriod(
        first=first, last=last + timedelta(hours=1), hours=hours, days=len(days),
        surface_station=header.sf_id, upper_air_station=header.ua_id,
    )


# Example usage
if __name__ == "__main__":
    print("PyAERMOD AERMET Input Generator")
    print("=" * 70)
    print()

    # Example: Create Stage 3 input (most common use case)
    station = AERMETStation(
        station_id="KORD",
        station_name="Chicago O'Hare",
        latitude=41.98,
        longitude=-87.90,
        time_zone=-6,
        elevation=200.0,
        anemometer_height=10.0
    )

    # Typical values for mixed urban/suburban area
    stage3 = AERMETStage3(
        job_id="EXAMPLE_STAGE3",
        merge_file="stage2.mrg",
        station=station,
        # Seasonal surface characteristics
        albedo=[0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50],
        bowen=[1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50],
        roughness=[0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50],
        start_date="2020/01/01",
        end_date="2020/12/31"
    )

    # Generate input file
    with open("aermet_stage3.inp", "w") as f:
        f.write(stage3.to_aermet_input())

    print("✓ Created: aermet_stage3.inp")
    print()
    print("To run AERMET Stage 3:")
    print("  aermet < aermet_stage3.inp")
    print()
    print("Output files:")
    print("  - aermod.sfc (surface parameters)")
    print("  - aermod.pfl (profile data)")
    print()

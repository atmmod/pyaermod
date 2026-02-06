"""
PyAERMOD AERMET Input Generator

Generates AERMET input files for meteorological data preprocessing.
AERMET is the EPA's meteorological preprocessor for AERMOD.

Compatible with AERMET version 24142.

Processing stages:
1. Stage 1: Extract and QA/QC observational data
2. Stage 3 (METPREP): Calculate boundary layer parameters and generate .sfc/.pfl

Note: The old Stage 2 MERGE pathway is obsolete in AERMET v24142.
Stage 1 EXTRACT output feeds directly into METPREP (Stage 3).
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path


def _format_lat(decimal_degrees: float) -> str:
    """Convert decimal latitude to AERMET format (e.g., 41.96N)"""
    hemisphere = "N" if decimal_degrees >= 0 else "S"
    return f"{abs(decimal_degrees):.4f}{hemisphere}"


def _format_lon(decimal_degrees: float) -> str:
    """Convert decimal longitude to AERMET format (e.g., 87.93W)"""
    hemisphere = "E" if decimal_degrees >= 0 else "W"
    return f"{abs(decimal_degrees):.4f}{hemisphere}"


def _gmt_offset(time_zone: int) -> int:
    """
    Convert UTC offset to AERMET LST-to-GMT adjustment.

    AERMET expects the number of hours to ADD to LST to get GMT.
    For US Central (UTC-6): LST + 6 = GMT, so offset = 6.

    Args:
        time_zone: UTC offset (e.g., -6 for CST, -5 for EST)

    Returns:
        Positive integer for Western Hemisphere
    """
    return -time_zone


@dataclass
class AERMETStation:
    """Surface meteorological station information"""
    station_id: str
    station_name: str
    latitude: float  # decimal degrees (positive=N, negative=S)
    longitude: float  # decimal degrees (positive=E, negative=W)
    time_zone: int  # UTC offset (e.g., -6 for CST, -5 for EST)

    # Optional parameters
    elevation: Optional[float] = None  # meters
    anemometer_height: float = 10.0  # meters

    def location_line(self) -> str:
        """Generate AERMET LOCATION keyword line"""
        parts = [
            f"   LOCATION   {self.station_id}",
            _format_lat(self.latitude),
            _format_lon(self.longitude),
            str(_gmt_offset(self.time_zone)),
        ]
        if self.elevation is not None:
            parts.append(f"{self.elevation:.1f}")
        return " ".join(parts)


@dataclass
class UpperAirStation:
    """Upper air (radiosonde) station information"""
    station_id: str
    station_name: str
    latitude: float
    longitude: float


@dataclass
class SurfaceCharacteristics:
    """
    Surface characteristics for a wind direction sector.

    Used with FREQ_SECT / SECTOR / SITE_CHAR keywords in METPREP.
    """
    # Frequency index (1-based, depends on FREQ_SECT setting)
    # For ANNUAL: always 1
    # For SEASONAL: 1=winter, 2=spring, 3=summer, 4=fall
    # For MONTHLY: 1-12
    freq_index: int

    # Sector number (1-based)
    sector: int

    # Surface parameters
    albedo: float  # 0.0-1.0
    bowen: float  # Bowen ratio
    roughness: float  # Surface roughness length z0 (meters)


@dataclass
class AERMETStage1:
    """
    AERMET Stage 1: Extract and QA/QC observational data

    Reads raw meteorological data and performs quality assurance.
    Valid SURFACE keywords: DATA, EXTRACT, QAOUT, XDATES, LOCATION,
    NO_MISSING, RANGE, AUDIT, MODIFY.
    """

    # Job control
    job_id: str = "STAGE1"
    messages: int = 2  # Message level (1=few, 2=normal, 3=verbose)

    # Surface data
    surface_station: Optional[AERMETStation] = None
    surface_data_file: Optional[str] = None
    surface_format: str = "ISHD"  # or "HUSWO", "SCRAM", "SAMSON", "CD144"

    # Upper air data
    upper_air_station: Optional[UpperAirStation] = None
    upper_air_data_file: Optional[str] = None
    upper_air_format: str = "FSL"

    # Date range
    start_date: str = "2020/01/01"  # YYYY/MM/DD
    end_date: str = "2020/12/31"

    # Output
    output_file: str = "stage1.rpt"
    extract_file: str = "stage1_sfc.ext"
    qa_file: Optional[str] = None

    # Optional: variables that must not be missing
    no_missing: Optional[List[str]] = None

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
            ua_extract = self.extract_file.replace('.ext', '_ua.ext')
            lines.append("UPPERAIR")
            lines.append(f"   DATA       {self.upper_air_data_file} {self.upper_air_format}")
            lines.append(f"   EXTRACT    {ua_extract}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
            loc = self.upper_air_station
            lines.append(f"   LOCATION   {loc.station_id} "
                         f"{_format_lat(loc.latitude)} "
                         f"{_format_lon(loc.longitude)}")
            lines.append("")

        # SURFACE pathway
        if self.surface_station and self.surface_data_file:
            lines.append("SURFACE")
            lines.append(f"   DATA       {self.surface_data_file} {self.surface_format}")
            lines.append(f"   EXTRACT    {self.extract_file}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")

            # LOCATION: station_id lat lon gmt_offset [elevation]
            lines.append(self.surface_station.location_line())

            # Optional: NO_MISSING
            if self.no_missing:
                var_str = " ".join(self.no_missing)
                lines.append(f"   NO_MISSING  {var_str}")

            # Optional: QAOUT
            if self.qa_file:
                lines.append(f"   QAOUT      {self.qa_file}")

            lines.append("")

        return "\n".join(lines)


@dataclass
class AERMETStage3:
    """
    AERMET Stage 3 (METPREP): Calculate boundary layer parameters

    Produces final AERMOD-ready meteorology files (.sfc and .pfl).

    In AERMET v24142, the old MERGE pathway is obsolete. The Stage 1
    EXTRACT file feeds directly into METPREP via the SURFACE QAOUT keyword.

    Surface characteristics are specified using FREQ_SECT/SECTOR/SITE_CHAR
    (NOT the old ALBEDO/BOWEN/ROUGHNESS keywords).
    """

    # Job control
    job_id: str = "STAGE3"
    messages: int = 2

    # Input from Stage 1 (the extract file)
    surface_extract: str = "stage1_sfc.ext"

    # Upper air extract (optional)
    upper_air_extract: Optional[str] = None

    # Station info
    station: Optional[AERMETStation] = None

    # Surface characteristics frequency
    # Options: "ANNUAL", "SEASONAL", "MONTHLY"
    frequency: str = "ANNUAL"

    # Number of wind direction sectors (1-16)
    num_sectors: int = 1

    # Sector boundaries: list of (sector_num, start_dir, end_dir)
    # For 1 sector: [(1, 0, 360)]
    sectors: List[Tuple[int, int, int]] = field(default_factory=lambda: [(1, 0, 360)])

    # Surface characteristics: list of SurfaceCharacteristics
    # If empty, will auto-generate from albedo/bowen/roughness defaults
    site_chars: List[SurfaceCharacteristics] = field(default_factory=list)

    # Simple interface: monthly albedo, bowen, roughness (12 values each)
    # Used when site_chars is empty
    albedo: List[float] = field(default_factory=lambda: [0.15] * 12)
    bowen: List[float] = field(default_factory=lambda: [1.0] * 12)
    roughness: List[float] = field(default_factory=lambda: [0.1] * 12)

    # NWS anemometer height
    nws_wind_height: float = 10.0  # meters

    # METHOD options
    methods: List[Tuple[str, str]] = field(default_factory=lambda: [
        ("REFLEVEL", "SUBNWS"),
    ])

    # Date range
    start_date: str = "2020/01/01"
    end_date: str = "2020/12/31"

    # Output files
    output_file: str = "stage3.rpt"
    surface_file: str = "aermod.sfc"
    profile_file: str = "aermod.pfl"

    def _build_site_chars(self) -> List[SurfaceCharacteristics]:
        """
        Auto-generate SITE_CHAR entries from albedo/bowen/roughness lists.

        Maps frequency type to the correct number of entries:
        - ANNUAL: 1 entry per sector (use average of 12 monthly values)
        - SEASONAL: 4 entries per sector (winter=DJF, spring=MAM, summer=JJA, fall=SON)
        - MONTHLY: 12 entries per sector
        """
        chars = []

        if self.frequency == "ANNUAL":
            avg_albedo = sum(self.albedo) / len(self.albedo)
            avg_bowen = sum(self.bowen) / len(self.bowen)
            avg_rough = sum(self.roughness) / len(self.roughness)
            for s in range(1, self.num_sectors + 1):
                chars.append(SurfaceCharacteristics(
                    freq_index=1, sector=s,
                    albedo=avg_albedo, bowen=avg_bowen, roughness=avg_rough
                ))
        elif self.frequency == "SEASONAL":
            # Winter=DJF(12,1,2), Spring=MAM(3,4,5), Summer=JJA(6,7,8), Fall=SON(9,10,11)
            season_months = [(11, 0, 1), (2, 3, 4), (5, 6, 7), (8, 9, 10)]
            for season_idx, months in enumerate(season_months, 1):
                s_albedo = sum(self.albedo[m] for m in months) / 3
                s_bowen = sum(self.bowen[m] for m in months) / 3
                s_rough = sum(self.roughness[m] for m in months) / 3
                for s in range(1, self.num_sectors + 1):
                    chars.append(SurfaceCharacteristics(
                        freq_index=season_idx, sector=s,
                        albedo=s_albedo, bowen=s_bowen, roughness=s_rough
                    ))
        elif self.frequency == "MONTHLY":
            for month in range(1, 13):
                for s in range(1, self.num_sectors + 1):
                    chars.append(SurfaceCharacteristics(
                        freq_index=month, sector=s,
                        albedo=self.albedo[month - 1],
                        bowen=self.bowen[month - 1],
                        roughness=self.roughness[month - 1]
                    ))

        return chars

    def to_aermet_input(self) -> str:
        """Generate AERMET Stage 3 (METPREP) input file"""
        lines = []

        # Header
        lines.append("** AERMET Stage 3 (METPREP) Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway
        lines.append("JOB")
        lines.append(f"   REPORT     {self.output_file}")
        lines.append(f"   MESSAGES   {self.messages}")
        lines.append("")

        # UPPERAIR pathway (if upper air data available)
        if self.upper_air_extract:
            lines.append("UPPERAIR")
            lines.append(f"   QAOUT      {self.upper_air_extract}")
            lines.append("")

        # SURFACE pathway — reads Stage 1 extract via QAOUT
        lines.append("SURFACE")
        lines.append(f"   QAOUT      {self.surface_extract}")
        lines.append("")

        # METPREP pathway
        lines.append("METPREP")

        # XDATES
        lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")

        # LOCATION
        if self.station:
            lines.append(self.station.location_line())

        # NWS anemometer height
        lines.append(f"   NWS_HGT    WIND {self.nws_wind_height:.1f}")

        # Surface characteristics
        lines.append(f"   FREQ_SECT  {self.frequency} {self.num_sectors}")

        # SECTOR definitions
        for sector_num, start_dir, end_dir in self.sectors:
            lines.append(f"   SECTOR     {sector_num} {start_dir} {end_dir}")

        # SITE_CHAR entries
        chars = self.site_chars if self.site_chars else self._build_site_chars()
        for sc in chars:
            lines.append(f"   SITE_CHAR  {sc.freq_index} {sc.sector} "
                         f"{sc.albedo:.4f} {sc.bowen:.4f} {sc.roughness:.4f}")

        # METHOD keywords
        for process, action in self.methods:
            lines.append(f"   METHOD     {process} {action}")

        # Output files
        lines.append(f"   OUTPUT     {self.surface_file}")
        lines.append(f"   PROFILE    {self.profile_file}")

        lines.append("")

        return "\n".join(lines)


def generate_fsl_upper_air(
    output_file: str,
    ua_station: UpperAirStation,
    start_year: int = 2023,
    end_year: int = 2023,
    elevation: int = 178,
    seed: int = 42,
) -> str:
    """
    Generate synthetic FSL-format upper air sounding data.

    Creates twice-daily (00Z and 12Z) soundings with climatologically
    reasonable temperature, humidity, and wind profiles. The data is
    synthetic but structurally valid for AERMET processing.

    FSL format column requirements:
    - Type 254: free format (linetype hour day month year)
    - Type 1: free format (linetype wban wmo lat lon elev release_time)
    - Type 2: free format (linetype checks... nlevs)
    - Type 3: fixed format, wind units at columns 48-49
    - Types 4-9: free format (linetype pres hgt temp dew wdir wspd)

    Args:
        output_file: Path to write FSL file
        ua_station: UpperAirStation with station info
        start_year: First year of data
        end_year: Last year of data
        elevation: Station elevation in meters
        seed: Random seed for reproducibility

    Returns:
        Path to the generated FSL file
    """
    import random
    import math

    random.seed(seed)

    MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
    DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

    wmo_id = ua_station.station_id
    lat_100 = int(ua_station.latitude * 100)
    lon_100 = int(ua_station.longitude * 100)

    # Type 3 line: wind units "kt" must be at columns 48-49
    # Format: '(47x,a2)' in Fortran
    type3_line = f"      3                                        kt    {wmo_id}"

    # Monthly base surface temperatures (tenths of deg C)
    base_temps = [-50, -30, 30, 100, 170, 230, 260, 250, 200, 120, 50, -30]

    lines = []

    for year in range(start_year, end_year + 1):
        for month_idx in range(12):
            month_name = MONTHS[month_idx]
            days = DAYS_IN_MONTH[month_idx]
            # Handle leap years
            if month_idx == 1 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
                days = 29

            base_temp = base_temps[month_idx]

            for day in range(1, days + 1):
                for hour in [0, 12]:
                    diurnal = 15 if hour == 12 else -5
                    perturb = random.randint(-20, 20)
                    sfc_temp = base_temp + diurnal + perturb
                    sfc_dew = sfc_temp - 50 - random.randint(0, 30)
                    sfc_wdir = 240 + random.randint(-40, 40)
                    sfc_wspd = 5 + random.randint(0, 15)

                    # Headers
                    lines.append(f"    254     {hour:2d}    {day:2d}   {month_name}   {year}")
                    lines.append(f"      1  99999  {wmo_id}   {lat_100}   {lon_100}       {elevation}  99999")
                    lines.append(f"      2  99999  99999  99999     11  99999  99999")
                    lines.append(type3_line)

                    # Type 9: Surface level (pressure*10 for FSL v2)
                    sfc_pres = 10000  # 1000.0 mb * 10
                    lines.append(
                        f"      9  {sfc_pres:5d}      {elevation}"
                        f"    {sfc_temp:4d}    {sfc_dew:4d}    {sfc_wdir:3d}     {sfc_wspd:2d}"
                    )

                    # Type 4: Mandatory levels
                    mandatory = [
                        (9250,  750,  -43,  1,  2),
                        (8500, 1500,  -85,  2,  6),
                        (7000, 3000, -183,  5, 14),
                        (5000, 5500, -340, 10, 26),
                        (3000, 9000, -560, 15, 44),
                        (2000, 12000, -680, 20, 59),
                    ]
                    for pres, hgt, temp_off, wdir_off, wspd_add in mandatory:
                        temp = sfc_temp + temp_off + random.randint(-10, 10)
                        dew = temp - 70 - random.randint(0, 50)
                        wdir = (sfc_wdir + wdir_off) % 360
                        wspd = sfc_wspd + wspd_add + random.randint(-3, 3)
                        lines.append(
                            f"      4  {pres:5d}     {hgt:4d}"
                            f"    {temp:4d}    {dew:4d}    {wdir:3d}     {wspd:2d}"
                        )

    with open(output_file, 'w') as f:
        f.write("\n".join(lines) + "\n")

    return output_file


def run_aermet_stages(
    aermet_exe: str,
    station: AERMETStation,
    surface_data_file: str,
    surface_format: str = "ISHD",
    upper_air_station: Optional[UpperAirStation] = None,
    upper_air_data_file: Optional[str] = None,
    upper_air_format: str = "FSL",
    start_date: str = "2023/01/01",
    end_date: str = "2023/12/31",
    output_dir: str = ".",
    albedo: Optional[List[float]] = None,
    bowen: Optional[List[float]] = None,
    roughness: Optional[List[float]] = None,
    frequency: str = "ANNUAL",
) -> dict:
    """
    Run complete AERMET processing (Stage 1 + Stage 3).

    Args:
        aermet_exe: Path to AERMET executable
        station: AERMETStation with location info
        surface_data_file: Path to raw surface data (e.g., ISHD file)
        surface_format: Data format (ISHD, HUSWO, etc.)
        upper_air_station: UpperAirStation (optional but recommended)
        upper_air_data_file: Path to upper air data (e.g., FSL file)
        upper_air_format: Upper air format (FSL, TD6201, etc.)
        start_date: Start date YYYY/MM/DD
        end_date: End date YYYY/MM/DD
        output_dir: Output directory
        albedo: Monthly albedo values (12 values), defaults to 0.15
        bowen: Monthly Bowen ratio values (12 values), defaults to 1.0
        roughness: Monthly roughness values (12 values), defaults to 0.1
        frequency: Surface char frequency (ANNUAL, SEASONAL, MONTHLY)

    Returns:
        Dict with paths to generated files
    """
    import subprocess

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if albedo is None:
        albedo = [0.15] * 12
    if bowen is None:
        bowen = [1.0] * 12
    if roughness is None:
        roughness = [0.1] * 12

    # --- Stage 1: Extract surface data ---
    stage1 = AERMETStage1(
        surface_station=station,
        surface_data_file=surface_data_file,
        surface_format=surface_format,
        start_date=start_date,
        end_date=end_date,
        output_file="stage1.rpt",
        extract_file="stage1_sfc.ext",
    )

    # Add upper air if provided
    if upper_air_station and upper_air_data_file:
        stage1.upper_air_station = upper_air_station
        stage1.upper_air_data_file = upper_air_data_file
        stage1.upper_air_format = upper_air_format

    stage1_inp = output_dir / "stage1.inp"
    with open(stage1_inp, 'w') as f:
        f.write(stage1.to_aermet_input())
    print(f"  Created: {stage1_inp}")

    print("  Running AERMET Stage 1...")
    result = subprocess.run(
        [aermet_exe, "stage1.inp"],
        capture_output=True, text=True, timeout=300,
        cwd=output_dir
    )

    # Check for success
    rpt = output_dir / "stage1.rpt"
    if rpt.exists():
        rpt_text = rpt.read_text()
        if "FINISHED SUCCESSFULLY" not in rpt_text:
            msg_file = output_dir / str(stage1.messages)
            msg_text = msg_file.read_text() if msg_file.exists() else "No messages"
            raise RuntimeError(f"AERMET Stage 1 failed.\nMessages:\n{msg_text}")

    print("  Stage 1 completed successfully.")

    # Determine upper air extract file
    ua_extract = None
    if upper_air_station and upper_air_data_file:
        ua_extract = "stage1_ua.ext"

    # --- Stage 3 (METPREP): Generate .sfc and .pfl ---
    stage3 = AERMETStage3(
        surface_extract="stage1_sfc.ext",
        upper_air_extract=ua_extract,
        station=station,
        frequency=frequency,
        num_sectors=1,
        sectors=[(1, 0, 360)],
        albedo=albedo,
        bowen=bowen,
        roughness=roughness,
        nws_wind_height=station.anemometer_height,
        start_date=start_date,
        end_date=end_date,
        output_file="stage3.rpt",
        surface_file="aermod.sfc",
        profile_file="aermod.pfl",
    )

    stage3_inp = output_dir / "stage3.inp"
    with open(stage3_inp, 'w') as f:
        f.write(stage3.to_aermet_input())
    print(f"  Created: {stage3_inp}")

    print("  Running AERMET Stage 3 (METPREP)...")
    result = subprocess.run(
        [aermet_exe, "stage3.inp"],
        capture_output=True, text=True, timeout=300,
        cwd=output_dir
    )

    rpt = output_dir / "stage3.rpt"
    if rpt.exists():
        rpt_text = rpt.read_text()
        if "FINISHED SUCCESSFULLY" not in rpt_text:
            msg_file = output_dir / str(stage3.messages)
            msg_text = msg_file.read_text() if msg_file.exists() else "No messages"
            raise RuntimeError(f"AERMET Stage 3 failed.\nMessages:\n{msg_text}")

    print("  Stage 3 completed successfully.")

    sfc_path = output_dir / "aermod.sfc"
    pfl_path = output_dir / "aermod.pfl"

    return {
        'stage1_input': str(stage1_inp),
        'stage3_input': str(stage3_inp),
        'surface_extract': str(output_dir / "stage1_sfc.ext"),
        'upper_air_extract': str(output_dir / "stage1_ua.ext") if ua_extract else None,
        'aermod_sfc': str(sfc_path) if sfc_path.exists() and sfc_path.stat().st_size > 0 else None,
        'aermod_pfl': str(pfl_path) if pfl_path.exists() and pfl_path.stat().st_size > 0 else None,
    }


# Example usage
if __name__ == "__main__":
    print("PyAERMOD AERMET Input Generator")
    print("=" * 70)
    print()

    # Example: Create Stage 3 input (most common use case)
    station = AERMETStation(
        station_id="94846",
        station_name="Chicago O'Hare",
        latitude=41.96,
        longitude=-87.93,
        time_zone=-6,
        elevation=205.0,
        anemometer_height=10.0
    )

    # Typical values for mixed urban/suburban area
    stage3 = AERMETStage3(
        surface_extract="stage1_sfc.ext",
        station=station,
        frequency="MONTHLY",
        num_sectors=1,
        sectors=[(1, 0, 360)],
        albedo=[0.50, 0.50, 0.40, 0.20, 0.15, 0.15, 0.15, 0.15, 0.20, 0.30, 0.40, 0.50],
        bowen=[1.50, 1.50, 1.00, 0.80, 0.70, 0.70, 0.70, 0.70, 0.80, 1.00, 1.50, 1.50],
        roughness=[0.50, 0.50, 0.50, 0.40, 0.30, 0.25, 0.25, 0.25, 0.30, 0.40, 0.50, 0.50],
        start_date="2023/01/01",
        end_date="2023/12/31"
    )

    # Generate input file
    with open("aermet_stage3.inp", "w") as f:
        f.write(stage3.to_aermet_input())

    print("Created: aermet_stage3.inp")
    print()
    print("To run AERMET Stage 3:")
    print("  aermet aermet_stage3.inp")
    print()
    print("Output files:")
    print("  - aermod.sfc (surface parameters)")
    print("  - aermod.pfl (profile data)")
    print()

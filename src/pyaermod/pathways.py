"""
PyAERMOD Pathway dataclasses — Control, Meteorology, Output, and Event pathways.

Also contains enums used across multiple pathways (TerrainType, PollutantType,
SourceType) and the chemistry-options cluster (ChemistryMethod, OzoneData,
ChemistryOptions).

This module is an internal implementation detail.  Public imports should go
through :mod:`pyaermod.input_generator` (the backwards-compatible facade)
or :mod:`pyaermod.api`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Union

if TYPE_CHECKING:
    from .sources import SourceGroupDefinition


def _normalize_title(text: Optional[str]) -> str:
    """Collapse a title's whitespace to match AERMOD's free-form runstream.

    EPA AERMOD reads a TITLEONE/TITLETWO field starting at the first
    non-blank character after the keyword, so leading and trailing
    whitespace is dropped, internal whitespace runs are not significant,
    and a title consisting only of whitespace becomes blank.  Titles are
    *not* quoted in the runstream, so the only faithful way to keep a
    write -> read round-trip stable is to emit the same normalized form
    the reader recovers (``input_reader`` joins the title tokens with a
    single space).  Returns ``""`` for an empty/all-whitespace title.
    """
    return " ".join((text or "").split())


# ============================================================================
# ENUMS
# ============================================================================

class TerrainType(Enum):
    """AERMOD terrain types"""
    FLAT = "FLAT"
    ELEVATED = "ELEVATED"
    FLATSRCS = "FLATSRCS"


class PollutantType(Enum):
    """Common pollutant types"""
    OTHER = "OTHER"
    PM25 = "PM25"
    PM10 = "PM10"
    NO2 = "NO2"
    SO2 = "SO2"
    CO = "CO"
    O3 = "O3"


class SourceType(Enum):
    """AERMOD source types"""
    POINT = "POINT"
    VOLUME = "VOLUME"
    AREA = "AREA"
    AREACIRC = "AREACIRC"
    AREAPOLY = "AREAPOLY"
    OPENPIT = "OPENPIT"
    LINE = "LINE"
    RLINE = "RLINE"
    RLINEXT = "RLINEXT"
    BUOYLINE = "BUOYLINE"


# ============================================================================
# NO2/SO2 CHEMISTRY OPTIONS
# ============================================================================

class ChemistryMethod(Enum):
    """AERMOD NO2 chemistry conversion methods."""
    OLM = "OLM"
    PVMRM = "PVMRM"
    ARM2 = "ARM2"
    GRSM = "GRSM"


@dataclass
class OzoneData:
    """
    Ozone data for NO2 chemistry options.

    Provide either an hourly ozone file, a uniform value, or
    sector-dependent values.

    Parameters
    ----------
    ozone_file : str, optional
        Path to hourly ozone data file.
    uniform_value : float, optional
        Uniform ozone concentration in ppb.
    sector_values : dict, optional
        Mapping of sector index to ozone value in ppb.
    """
    ozone_file: Optional[str] = None
    uniform_value: Optional[float] = None
    sector_values: Optional[Dict[int, float]] = None


@dataclass
class ChemistryOptions:
    """
    AERMOD NO2 chemistry configuration.

    Controls the NO2-to-NOx conversion method used in AERMOD.
    Requires pollutant to be NO2.

    Parameters
    ----------
    method : ChemistryMethod
        Chemistry algorithm (OLM, PVMRM, ARM2, GRSM).
    ozone_data : OzoneData, optional
        Ozone data for OLM/PVMRM/GRSM methods.
    default_no2_ratio : float
        Default in-stack NO2/NOx ratio (0-1). Default 0.5.
    olm_groups : list of SourceGroupDefinition
        Source groups for OLM method.
    nox_file : str, optional
        NOx background file (GRSM only).
    """
    method: ChemistryMethod = ChemistryMethod.ARM2
    ozone_data: Optional[OzoneData] = None
    default_no2_ratio: float = 0.5
    olm_groups: List[SourceGroupDefinition] = field(default_factory=list)
    nox_file: Optional[str] = None


# ============================================================================
# CONTROL PATHWAY
# ============================================================================

@dataclass
class ControlPathway:
    """
    AERMOD Control (CO) pathway configuration

    Defines overall model behavior, pollutant type, averaging periods,
    and other global settings.
    """
    title_one: str
    title_two: Optional[str] = None
    pollutant_id: Union[str, PollutantType] = PollutantType.OTHER
    averaging_periods: List[str] = field(default_factory=lambda: ["ANNUAL"])
    terrain_type: Union[str, TerrainType] = TerrainType.FLAT

    # Model options
    calculate_concentration: bool = True
    calculate_deposition: bool = False
    calculate_dry_deposition: bool = False
    calculate_wet_deposition: bool = False

    # Optional settings
    elevation_units: str = "METERS"  # or "FEET"
    flag_pole_height: Optional[float] = None
    half_life: Optional[float] = None  # hours, for decay
    decay_coefficient: Optional[float] = None  # 1/seconds

    # Regulatory default mode
    regulatory_default: bool = True  # Include DFAULT in MODELOPT

    # Urban/rural
    urban_option: Optional[str] = None  # Urban area name if urban
    urban_population: Optional[float] = None  # Required population for URBANOPT

    # Low wind options
    low_wind_option: Optional[str] = None  # e.g., "LOWWIND3"

    # Non-regulatory model options. AERMOD gates some source types and
    # features behind these: RLINEXT is rejected outright with
    # "Non-DFAULT ALPHA Option Required" unless ALPHA is present.
    alpha: bool = False
    beta: bool = False

    # Event file reference
    eventfil: Optional[str] = None

    # NO2 chemistry options
    chemistry: Optional[ChemistryOptions] = None

    def to_aermod_input(self) -> str:
        """Generate AERMOD CO pathway text"""
        lines = ["CO STARTING"]

        # Titles — normalize whitespace so the emitted line reads back to
        # itself (AERMOD does not quote titles; see _normalize_title).
        title_one = _normalize_title(self.title_one)
        lines.append(f"   TITLEONE  {title_one}".rstrip())
        title_two = _normalize_title(self.title_two)
        if title_two:
            lines.append(f"   TITLETWO  {title_two}")

        # Model options
        model_opts = []
        if self.calculate_concentration:
            model_opts.append("CONC")
        if self.calculate_deposition:
            model_opts.append("DEPOS")
        if self.calculate_dry_deposition:
            model_opts.append("DDEP")
        if self.calculate_wet_deposition:
            model_opts.append("WDEP")

        # Add terrain type
        terrain = self.terrain_type.value if isinstance(self.terrain_type, TerrainType) else self.terrain_type
        model_opts.append(terrain)

        # Regulatory default mode
        if self.regulatory_default:
            model_opts.append("DFAULT")

        # Non-regulatory options, which AERMOD requires before it will
        # accept certain source types and keywords.
        if self.alpha:
            model_opts.append("ALPHA")
        if self.beta:
            model_opts.append("BETA")

        # Append chemistry method to MODELOPT
        if self.chemistry is not None:
            model_opts.append(self.chemistry.method.value)

        lines.append(f"   MODELOPT  {' '.join(model_opts)}")

        # Averaging periods
        lines.append(f"   AVERTIME  {' '.join(self.averaging_periods)}")

        # Pollutant ID
        pollutant = self.pollutant_id.value if isinstance(self.pollutant_id, PollutantType) else self.pollutant_id
        lines.append(f"   POLLUTID  {pollutant}")

        # Optional parameters
        if self.half_life is not None:
            lines.append(f"   HALFLIFE  {self.half_life:.4f}")

        if self.decay_coefficient is not None:
            lines.append(f"   DCAYCOEF  {self.decay_coefficient:.6e}")

        if self.elevation_units != "METERS":
            lines.append(f"   ELEVUNIT  {self.elevation_units}")

        if self.flag_pole_height is not None:
            lines.append(f"   FLAGPOLE  {self.flag_pole_height:.2f}")

        if self.urban_option:
            # URBANOPT format: UrbanID Population [Name] [Roughness]
            pop = self.urban_population or 1000000.0
            lines.append(f"   URBANOPT  {self.urban_option}  {pop:.1f}")

        if self.low_wind_option:
            lines.append(f"   LOW_WIND  {self.low_wind_option}")

        # Chemistry-related CO keywords
        if self.chemistry is not None:
            chem = self.chemistry
            # O3VALUES
            if chem.ozone_data is not None:
                oz = chem.ozone_data
                if oz.ozone_file:
                    lines.append(f"   O3VALUES  {oz.ozone_file}")
                elif oz.uniform_value is not None:
                    lines.append(f"   O3VALUES  UNIFORM  {oz.uniform_value:.4g}")
                elif oz.sector_values:
                    for sector_id, value in sorted(oz.sector_values.items()):
                        lines.append(f"   O3VALUES  SECTOR  {sector_id}  {value:.4g}")

            # NO2STACK (default in-stack ratio)
            lines.append(f"   NO2STACK  {chem.default_no2_ratio:.4f}")

            # NOx background file (GRSM)
            if chem.nox_file:
                lines.append(f"   NOXVALUE  {chem.nox_file}")

        # Event file reference
        if self.eventfil:
            lines.append(f"   EVENTFIL  {self.eventfil}")

        # Run command
        lines.append("   RUNORNOT  RUN")
        lines.append("CO FINISHED")

        return "\n".join(lines)


# ============================================================================
# METEOROLOGY PATHWAY
# ============================================================================

@dataclass
class MeteorologyPathway:
    """
    AERMOD Meteorology (ME) pathway

    Defines meteorological data files and processing options.

    AERMOD requires five mandatory ME keywords:
      SURFFILE  -- path to the .sfc file
      PROFFILE  -- path to the .pfl file
      SURFDATA  -- surface station ID + start year
      UAIRDATA  -- upper-air station ID + start year
      PROFBASE  -- base elevation (m MSL) of the profile data
    """
    surface_file: str
    profile_file: str

    # Station identification (mandatory for AERMOD)
    surface_station_id: int = 0          # SURFDATA station ID (e.g. WBAN or numeric)
    upper_air_station_id: int = 0        # UAIRDATA station ID
    data_start_year: int = 2020          # Start year for SURFDATA/UAIRDATA

    # Profile base elevation (mandatory)
    profile_base_elevation: float = 0.0  # meters MSL

    # Optional parameters
    start_year: Optional[int] = None
    start_month: Optional[int] = None
    start_day: Optional[int] = None
    end_year: Optional[int] = None
    end_month: Optional[int] = None
    end_day: Optional[int] = None

    # Wind direction rotation
    wind_rotation: Optional[float] = None  # degrees

    def to_aermod_input(self) -> str:
        """Generate AERMOD ME pathway text"""
        lines = ["ME STARTING"]

        # Surface and profile files
        lines.append(f"   SURFFILE  {self.surface_file}")
        lines.append(f"   PROFFILE  {self.profile_file}")

        # Station data (mandatory)
        lines.append(f"   SURFDATA  {self.surface_station_id}  {self.data_start_year}")
        lines.append(f"   UAIRDATA  {self.upper_air_station_id}  {self.data_start_year}")
        lines.append(f"   PROFBASE  {self.profile_base_elevation:.1f}  METERS")

        # Date range (if specified)
        if all(x is not None for x in [self.start_year, self.start_month, self.start_day,
                                        self.end_year, self.end_month, self.end_day]):
            lines.append(
                f"   STARTEND  {self.start_year:4d} {self.start_month:2d} {self.start_day:2d}  "
                f"{self.end_year:4d} {self.end_month:2d} {self.end_day:2d}"
            )

        # Wind rotation
        if self.wind_rotation is not None:
            lines.append(f"   WDROTATE  {self.wind_rotation:.2f}")

        lines.append("ME FINISHED")
        return "\n".join(lines)


# ============================================================================
# OUTPUT PATHWAY
# ============================================================================

@dataclass
class OutputPathway:
    """
    AERMOD Output (OU) pathway

    Controls output file generation and formats.
    """
    # Table outputs
    receptor_table: bool = True
    receptor_table_rank: int = 10  # Number of high values to include

    max_table: bool = True
    max_table_rank: int = 10

    day_table: bool = False

    # File outputs
    summary_file: Optional[str] = None
    max_file: Optional[str] = None
    plot_file: Optional[str] = None
    plot_file_averaging: str = "ANNUAL"  # Averaging period for default PLOTFILE

    # POSTFILE outputs
    postfile: Optional[str] = None  # Output file path
    postfile_averaging: Optional[str] = None  # e.g. "1" for 1-HR, "ANNUAL", etc.
    postfile_source_group: str = "ALL"
    postfile_format: str = "PLOT"  # PLOT (formatted) or UNFORM (unformatted/binary)

    # Per-group plot files: list of (averaging_period, source_group, filename)
    plot_file_groups: List[Tuple[str, str, str]] = field(default_factory=list)

    # Output type (CONC, DEPOS, DDEP, WDEP, DETH)
    output_type: str = "CONC"

    def to_aermod_input(self) -> str:
        """Generate AERMOD OU pathway text"""
        lines = ["OU STARTING"]

        # Receptor table
        if self.receptor_table:
            lines.append(f"   RECTABLE  ALLAVE  {self.receptor_table_rank}")

        # Max table
        if self.max_table:
            lines.append(f"   MAXTABLE  ALLAVE  {self.max_table_rank}")

        # Day table
        if self.day_table:
            lines.append("   DAYTABLE  ALLAVE")

        # Summary file
        if self.summary_file:
            lines.append(f"   SUMMFILE  {self.summary_file}")

        # Max file
        if self.max_file:
            lines.append(f"   MAXIFILE  {self.max_file}")

        # Plot file
        if self.plot_file:
            lines.append(
                f"   PLOTFILE  {self.plot_file_averaging}  ALL  {self.output_type}  FIRST  {self.plot_file}"
            )

        # Per-group plot files
        for avg_period, src_group, filename in self.plot_file_groups:
            lines.append(
                f"   PLOTFILE  {avg_period}  {src_group}  "
                f"{self.output_type}  FIRST  {filename}"
            )

        # Postfile
        if self.postfile:
            ave = self.postfile_averaging or "ANNUAL"
            lines.append(
                f"   POSTFILE  {ave}  {self.postfile_source_group}  "
                f"{self.output_type}  {self.postfile_format}  {self.postfile}"
            )

        lines.append("OU FINISHED")
        return "\n".join(lines)


# ============================================================================
# EVENT PATHWAY
# ============================================================================

@dataclass
class EventPeriod:
    """A single AERMOD event period definition."""
    event_name: str
    start_date: str  # YYMMDDHH format
    end_date: str    # YYMMDDHH format
    source_group: str = "ALL"


@dataclass
class EventPathway:
    """
    AERMOD Event (EV) pathway.

    Defines specific time periods for event-based processing.
    Written as a separate file referenced by EVENTFIL in the CO pathway.
    """
    events: List[EventPeriod] = field(default_factory=list)

    def add_event(self, event: EventPeriod):
        """Add an event period."""
        self.events.append(event)

    def to_aermod_input(self) -> str:
        """Generate AERMOD EV pathway text."""
        lines = ["EV STARTING"]
        for event in self.events:
            lines.append(
                f"   EVENTPER  {event.event_name:<8} "
                f"{event.start_date}  {event.end_date}  {event.source_group}"
            )
        lines.append("EV FINISHED")
        return "\n".join(lines)

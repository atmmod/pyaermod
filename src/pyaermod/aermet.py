"""
PyAERMOD AERMET Input Generator and Output Parser

Writes AERMET runstream (control) files and parses the AERMET output
files AERMOD reads (.SFC surface and .PFL profile).

AERMET is EPA's meteorological preprocessor for AERMOD. Since version 11
(and in the current releases, 24142 and 26135) it runs in two stages:

1. **Stage 1** reads the raw upper-air, surface and on-site data
   (``DATA``), writes what it read (``EXTRACT``) and the quality-assured
   data (``QAOUT``). :class:`AERMETStage1` writes this deck.
2. **Stage 2** reads the Stage 1 ``QAOUT`` files, merges them itself and
   computes the boundary-layer parameters on the ``METPREP`` pathway,
   writing the ``.SFC`` (``OUTPUT``) and ``.PFL`` (``PROFILE``) files.
   :class:`AERMETStage3` writes this deck.

The separate merge stage of AERMET 06341 and earlier (the ``MERGE``
pathway) no longer exists: AERMET ignores that pathway with warning W01.
:class:`AERMETStage2` is kept only so old code still imports; it is
deprecated and writes no deck. ``Stage3`` keeps its name, and the
``stage3.inp`` deck name, so existing pipelines keep their file names.

The keyword syntax follows the AERMET Fortran (``mod_read_input.f90``,
``mod_upperair.f90``, ``mod_surface.f90``, ``mod_onsite.f90``,
``mod_pbl.f90`` and ``getloc`` in ``mod_main1.f90`` of v24142 and
v26135). The rules the writers rely on are noted where they are used.
"""

import re
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

# ---------------------------------------------------------------------------
# Data formats AERMET accepts on the DATA keyword, and their time basis
# ---------------------------------------------------------------------------

#: Upper-air formats (``upformats`` in mod_upperair.f90). All are in GMT.
UPPER_AIR_FORMATS: Tuple[str, ...] = ("FSL", "IGRA", "6201FB", "6201VB")

#: Surface formats AERMET accepts (``sfformats`` in mod_surface.f90;
#: ``GHCN`` is new in v26135). ``3280VB`` and ``3280FB`` are listed there
#: but rejected as obsolete (error E04), so they are not offered here.
SURFACE_FORMATS: Tuple[str, ...] = (
    "ISHD", "CD144", "CD144FB", "SCRAM", "SAMSON", "HUSWO", "GHCN",
)

# LOCATION's fourth field is the GMT-to-LST adjustment AERMET applies to
# every observation it reads (data_dates in mod_main1.f90): LST = GMT - adj.
# It must be 0 for data already in local standard time. EPA's own decks
# show the basis of these formats: ISHD, FSL and 6201FB carry the site's
# hours west of Greenwich (cordero, EX01, EX04, salem), and CD144, SAMSON,
# HUSWO and on-site data carry 0 (EX01, EX03, lovett, martins_creek). The
# basis of SCRAM and GHCN is not shown by any EPA deck, so the writer asks
# for the adjustment explicitly rather than guess.
_GMT_SURFACE_FORMATS = frozenset({"ISHD"})
_LST_SURFACE_FORMATS = frozenset({"CD144", "CD144FB", "SAMSON", "HUSWO"})

#: Frequencies FREQ_SECT accepts (freq_sec in mod_pbl.f90), and the number
#: of periods each one has.
FREQUENCIES: Dict[str, int] = {"ANNUAL": 1, "SEASONAL": 4, "MONTHLY": 12}


def _num(value: float) -> str:
    """A number as AERMET's list-directed reads take it, without an exponent."""
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _lat(value: float) -> str:
    # coord() in mod_main1.f90 takes an unsigned number with one N/S/E/W suffix.
    return f"{_num(abs(value))}{'N' if value >= 0 else 'S'}"


def _lon(value: float) -> str:
    return f"{_num(abs(value))}{'E' if value >= 0 else 'W'}"


# getloc stores a LOCATION station ID in character(len=8) (sfid, upid, osid,
# pblid), so a longer ID is cut to its first eight characters.
_MAX_STATION_ID = 8


def _station_id(station_id: str) -> str:
    sid = str(station_id).strip()
    if not sid or any(ch.isspace() for ch in sid):
        raise ValueError(
            f"AERMET station IDs are one word (LOCATION reads the first field), got {station_id!r}"
        )
    if len(sid) > _MAX_STATION_ID:
        raise ValueError(
            f"AERMET keeps {_MAX_STATION_ID} characters of a LOCATION station ID "
            f"(character(len=8) in getloc), got {sid!r}"
        )
    return sid


def _surface_station_id(station_id: str) -> str:
    """The SURFACE LOCATION ID, which METPREP reads back as an integer (WBAN).

    read_ext in mod_surface.f90 (24142 and 26135) reads the ID in the
    Stage 1 QAOUT file with ``read(sfid,*)iwban`` and no iostat, so an ID
    such as ``KATL`` passes Stage 1 but crashes METPREP with "Bad integer
    for item 1 in list input".
    """
    sid = _station_id(station_id)
    if not (sid.isascii() and sid.isdigit()):
        raise ValueError(
            "the SURFACE station ID must be a number, normally the station's WBAN "
            "(13874 for Atlanta, not KATL): METPREP reads it back as an integer "
            f"(read_ext in mod_surface.f90) and stops on anything else, got {sid!r}"
        )
    return sid


def _filename(name: Union[str, Path]) -> str:
    """A file name for a DATA/EXTRACT/QAOUT/OUTPUT field, quoted if it has blanks."""
    text = str(name)
    if any(ch.isspace() for ch in text):
        return f'"{text}"'
    return text


def _location(station_id: str, latitude: float, longitude: float,
              adjustment: Optional[int] = None,
              elevation: Optional[float] = None) -> str:
    """The fields of a LOCATION keyword: ``id lat lon [adj [elev]]`` (getloc)."""
    fields = [_station_id(station_id), _lat(latitude), _lon(longitude)]
    if adjustment is not None:
        fields.append(str(int(adjustment)))
    if elevation is not None:
        if adjustment is None:
            raise ValueError("LOCATION takes the elevation only after the time adjustment")
        fields.append(_num(elevation))
    return " ".join(fields)


def _derived_name(name: str, tag: str) -> str:
    """``stage1.ext`` -> ``stage1_ua.ext``: a sibling file name for another pathway."""
    p = Path(name)
    return str(p.with_name(f"{p.stem}_{tag}{p.suffix}"))


def _format_or_raise(fmt: str, allowed: Sequence[str], what: str) -> str:
    value = str(fmt).strip().upper()
    if value not in allowed:
        raise ValueError(
            f"{what} format {fmt!r} is not one AERMET reads; use one of {', '.join(allowed)}"
        )
    return value


def _messages_file(messages: Optional[Union[int, str]], default: str, cls: str) -> str:
    """Resolve the legacy ``messages`` field to the MESSAGES file name.

    MESSAGES names a file (job_path in mod_read_input.f90); AERMET has no
    message level. The old integer level was written as a file named
    ``2``, so an integer is ignored with a warning.
    """
    if messages is None:
        return default
    if isinstance(messages, str):
        return messages
    warnings.warn(
        f"{cls}.messages={messages!r} is ignored: AERMET's MESSAGES keyword names a file "
        "and there is no message level; set message_file instead",
        DeprecationWarning, stacklevel=3,
    )
    return default


@dataclass
class AERMETStation:
    """Surface meteorological station information.

    ``time_zone`` is the UTC offset in hours, negative west of Greenwich
    (``-5`` for Eastern Standard Time). AERMET wants the opposite sign
    (hours to subtract from GMT), and only for data recorded in GMT; the
    writers convert it (see :class:`AERMETStage1`).

    ``station_id`` is the station's WBAN number (``13874`` for Atlanta
    Hartsfield, not the ICAO code ``KATL``) when the station is Stage 1's
    SURFACE station: METPREP reads that ID back as an integer and stops on
    anything else. AERMET keeps at most 8 characters of any station ID.
    """
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
    """Upper air (radiosonde) station information.

    AERMET 24142 and later stop with error E05 when the UPPERAIR LOCATION
    has no station elevation (upper_path in mod_upperair.f90), so
    ``elevation`` (metres) is needed to write a Stage 1 deck. ``time_zone``
    is the UTC offset as on :class:`AERMETStation`; when it is None the
    surface station's is used.
    """
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    elevation: Optional[float] = None  # meters
    time_zone: Optional[int] = None  # UTC offset; None = the surface station's

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"latitude must be between -90 and 90, got {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"longitude must be between -180 and 180, got {self.longitude}")


@dataclass
class OnsiteData:
    """Site-specific (ONSITE pathway) measurements for Stage 1.

    AERMET reads on-site data with a Fortran format the user supplies:
    each ``READ n`` record lists the variable names in the order they
    appear on the n-th line of an observation, and ``FORMAT n`` gives the
    Fortran format for that line. ``read_records[i]`` and
    ``format_records[i]`` are record ``i + 1``. Variable names are
    AERMET's (``OSYR OSMO OSDY OSHR``, ``HT01``, ``WS01``, ``WD01``,
    ``SA01``, ``TT01``, ...; see the AERMET user's guide).

    ``time_adjustment`` is written as LOCATION's GMT-to-LST field. On-site
    data are normally recorded in local standard time, for which it is 0
    (every EPA test case uses 0).

    ``threshold`` (m/s) is the THRESHOLD keyword, which AERMET requires
    when a wind speed is read (os_test in mod_onsite.f90).
    """
    station_id: str
    latitude: float
    longitude: float
    data_file: str
    read_records: List[List[str]]
    format_records: List[str]
    time_adjustment: int = 0
    elevation: Optional[float] = None
    threshold: Optional[float] = None
    heights: Optional[List[float]] = None  # OSHEIGHTS
    delta_temp: List[Tuple[int, float, float]] = field(default_factory=list)  # DELTA_TEMP n lower upper
    obs_per_hour: Optional[int] = None  # OBS/HOUR
    audit: List[str] = field(default_factory=list)
    qaout_file: str = "stage1_os.qa"
    extra_keywords: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"latitude must be between -90 and 90, got {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"longitude must be between -180 and 180, got {self.longitude}")
        if len(self.read_records) != len(self.format_records):
            raise ValueError(
                "read_records and format_records must pair up (AERMET requires one FORMAT "
                f"per READ); got {len(self.read_records)} and {len(self.format_records)}"
            )
        if not self.read_records:
            raise ValueError("ONSITE needs at least one READ/FORMAT record")

    def to_lines(self, start_date: str, end_date: str) -> List[str]:
        """The ONSITE pathway of a Stage 1 deck."""
        lines = ["ONSITE"]
        lines.append(f"   DATA       {_filename(self.data_file)}")
        lines.append(f"   QAOUT      {_filename(self.qaout_file)}")
        lines.append(f"   XDATES     {start_date} TO {end_date}")
        lines.append("   LOCATION   " + _location(
            self.station_id, self.latitude, self.longitude,
            self.time_adjustment, self.elevation))
        for n, (names, fmt) in enumerate(zip(self.read_records, self.format_records), start=1):
            lines.append(f"   READ {n}     " + " ".join(names))
            lines.append(f"   FORMAT {n}   {fmt}")
        if self.threshold is not None:
            lines.append(f"   THRESHOLD  {_num(self.threshold)}")
        if self.heights:
            lines.append("   OSHEIGHTS  " + " ".join(_num(h) for h in self.heights))
        for n, lower, upper in self.delta_temp:
            lines.append(f"   DELTA_TEMP {int(n)} {_num(lower)} {_num(upper)}")
        if self.obs_per_hour is not None:
            lines.append(f"   OBS/HOUR   {int(self.obs_per_hour)}")
        if self.audit:
            lines.append("   AUDIT      " + " ".join(self.audit))
        lines.extend(f"   {extra}" for extra in self.extra_keywords)
        lines.append("")
        return lines


@dataclass
class AERMETStage1:
    """
    AERMET Stage 1: extract and quality-assure the observations.

    Writes the UPPERAIR, SURFACE and (optionally) ONSITE pathways, each
    with DATA, EXTRACT (not ONSITE, which has none), QAOUT, XDATES and
    LOCATION. The QAOUT files are what :class:`AERMETStage3` reads.

    File names: ``output_file`` is the REPORT file, ``message_file`` the
    MESSAGES file, ``extract_file`` and ``qa_file`` the surface EXTRACT
    and QAOUT files. The upper-air EXTRACT and QAOUT default to the same
    names with ``_ua`` added (``stage1_ua.ext``, ``stage1_ua.qa``).

    Time adjustment (LOCATION's fourth field): AERMET subtracts it from
    every observation's hour, so it is ``-time_zone`` for data in GMT and
    0 for data in local standard time. The writer derives it from the data
    format (upper-air data and ISHD are GMT; CD144, CD144FB, SAMSON and
    HUSWO are LST). For SCRAM and GHCN surface data, set
    ``surface_time_adjustment``; it always overrides the derived value, as
    ``upper_air_time_adjustment`` does for upper air.
    """

    # Job control
    job_id: str = "STAGE1"
    messages: Optional[Union[int, str]] = None  # deprecated: see message_file

    # Surface data
    surface_station: Optional[AERMETStation] = None
    surface_data_file: Optional[str] = None
    surface_format: str = "ISHD"  # see SURFACE_FORMATS

    # Upper air data
    upper_air_station: Optional[UpperAirStation] = None
    upper_air_data_file: Optional[str] = None

    # Date range
    start_date: str = "2020/01/01"  # YYYY/MM/DD
    end_date: str = "2020/12/31"

    # Output
    output_file: str = "stage1.out"  # REPORT
    extract_file: str = "stage1.ext"  # surface EXTRACT
    qa_file: str = "stage1.qa"  # surface QAOUT

    message_file: str = "stage1.msg"  # MESSAGES
    upper_air_format: str = "FSL"  # see UPPER_AIR_FORMATS
    upper_air_extract_file: Optional[str] = None  # default: extract_file + "_ua"
    upper_air_qa_file: Optional[str] = None  # default: qa_file + "_ua"
    surface_time_adjustment: Optional[int] = None
    upper_air_time_adjustment: Optional[int] = None
    upper_air_audit: List[str] = field(default_factory=list)
    surface_audit: List[str] = field(default_factory=list)
    onsite: Optional[OnsiteData] = None
    upper_air_extra: List[str] = field(default_factory=list)
    surface_extra: List[str] = field(default_factory=list)

    @property
    def upper_air_extract(self) -> str:
        return self.upper_air_extract_file or _derived_name(self.extract_file, "ua")

    @property
    def upper_air_qaout(self) -> str:
        return self.upper_air_qa_file or _derived_name(self.qa_file, "ua")

    @property
    def has_upper_air(self) -> bool:
        return bool(self.upper_air_station and self.upper_air_data_file)

    @property
    def has_surface(self) -> bool:
        return bool(self.surface_station and self.surface_data_file)

    def _surface_adjustment(self, fmt: str) -> int:
        if self.surface_time_adjustment is not None:
            return int(self.surface_time_adjustment)
        assert self.surface_station is not None
        if fmt in _GMT_SURFACE_FORMATS:
            return -int(self.surface_station.time_zone)
        if fmt in _LST_SURFACE_FORMATS:
            return 0
        raise ValueError(
            f"set surface_time_adjustment for {fmt} data: no EPA deck shows whether "
            "AERMET reads that format in GMT or local standard time"
        )

    def _upper_air_adjustment(self) -> int:
        if self.upper_air_time_adjustment is not None:
            return int(self.upper_air_time_adjustment)
        assert self.upper_air_station is not None
        zone = self.upper_air_station.time_zone
        if zone is None and self.surface_station is not None:
            zone = self.surface_station.time_zone
        if zone is None:
            raise ValueError(
                "set UpperAirStation.time_zone (or upper_air_time_adjustment): upper-air "
                "data are in GMT and AERMET needs the site's GMT-to-LST adjustment"
            )
        return -int(zone)

    def to_aermet_input(self) -> str:
        """Generate the AERMET Stage 1 runstream."""
        lines = []

        # Header
        lines.append("** AERMET Stage 1 Input")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        # JOB pathway: REPORT and MESSAGES take file names (job_path).
        lines.append("JOB")
        lines.append(f"   REPORT     {_filename(self.output_file)}")
        lines.append(f"   MESSAGES   {_filename(_messages_file(self.messages, self.message_file, 'AERMETStage1'))}")
        lines.append("")

        if self.has_upper_air:
            ua, ua_data = self.upper_air_station, self.upper_air_data_file
            assert ua is not None and ua_data is not None
            fmt = _format_or_raise(self.upper_air_format, UPPER_AIR_FORMATS, "Upper-air")
            if ua.elevation is None:
                raise ValueError(
                    "UpperAirStation.elevation is required: AERMET stops with error E05 "
                    "when the UPPERAIR LOCATION has no station elevation"
                )
            lines.append("UPPERAIR")
            lines.append(f"   DATA       {_filename(ua_data)} {fmt}")
            lines.append(f"   EXTRACT    {_filename(self.upper_air_extract)}")
            lines.append(f"   QAOUT      {_filename(self.upper_air_qaout)}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
            lines.append("   LOCATION   " + _location(
                ua.station_id, ua.latitude, ua.longitude,
                self._upper_air_adjustment(), ua.elevation))
            if self.upper_air_audit:
                lines.append("   AUDIT      " + " ".join(self.upper_air_audit))
            lines.extend(f"   {extra}" for extra in self.upper_air_extra)
            lines.append("")

        if self.has_surface:
            sf, sf_data = self.surface_station, self.surface_data_file
            assert sf is not None and sf_data is not None
            fmt = _format_or_raise(self.surface_format, SURFACE_FORMATS, "Surface")
            lines.append("SURFACE")
            lines.append(f"   DATA       {_filename(sf_data)} {fmt}")
            lines.append(f"   EXTRACT    {_filename(self.extract_file)}")
            lines.append(f"   QAOUT      {_filename(self.qa_file)}")
            lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
            # SURFACE has no ANEMHGT or ELEVATION keyword: the elevation is
            # LOCATION's fifth field and the anemometer height is METPREP's
            # NWS_HGT (written by AERMETStage3).
            lines.append("   LOCATION   " + _location(
                _surface_station_id(sf.station_id), sf.latitude, sf.longitude,
                self._surface_adjustment(fmt), sf.elevation))
            if self.surface_audit:
                lines.append("   AUDIT      " + " ".join(self.surface_audit))
            lines.extend(f"   {extra}" for extra in self.surface_extra)
            lines.append("")

        if self.onsite is not None:
            lines.extend(self.onsite.to_lines(self.start_date, self.end_date))

        return "\n".join(lines)


@dataclass
class AERMETStage2:
    """
    Deprecated: the separate AERMET merge stage no longer exists.

    AERMET 11 and later merge the data inside the METPREP stage, which
    :class:`AERMETStage3` writes; AERMET ignores a MERGE pathway with
    warning W01. The class stays importable so existing code keeps
    running; :func:`pyaermod.aermet_runner.run_aermet_pipeline` skips it
    and :meth:`to_aermet_input` raises.
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

    def __post_init__(self):
        warnings.warn(
            "AERMETStage2 is deprecated: AERMET 11 and later have no merge stage "
            "(the MERGE pathway is ignored); AERMETStage3 reads the Stage 1 QAOUT files",
            DeprecationWarning, stacklevel=3,
        )

    def to_aermet_input(self) -> str:
        """Raise: there is no merge-stage deck AERMET 11 or later would run."""
        raise NotImplementedError(
            "AERMET 11 and later have no merge stage: run AERMETStage1, then "
            "AERMETStage3, which reads Stage 1's QAOUT files and merges them itself"
        )


SiteChar = Union[str, Tuple[int, int, float, float, float]]

def _site_char_block(suffix: str, frequency: Optional[str], num_sectors: int,
                     sectors: Sequence[Tuple[float, float]],
                     records: Sequence[SiteChar]) -> List[str]:
    """FREQ_SECT, SECTOR and SITE_CHAR lines (``suffix`` "2" for the secondary site).

    pbl_path requires FREQ_SECT before SECTOR and SITE_CHAR (error E76);
    SECTOR is ``index start end`` and SITE_CHAR ``period sector albedo
    bowen z0`` (sectors and site_char in mod_pbl.f90).
    """
    freq = (frequency or "ANNUAL").upper()
    nsec = int(num_sectors)
    secs = list(sectors) or ([(0.0, 360.0)] if nsec == 1 else [])
    if len(secs) != nsec:
        raise ValueError(f"num_sectors={nsec} needs {nsec} (start, end) sectors; got {len(secs)}")
    lines = [f"   FREQ_SECT{suffix or ' '} {freq} {nsec}"]
    lines.extend(f"   SECTOR{suffix or ' '}    {i} {_num(start)} {_num(end)}"
                 for i, (start, end) in enumerate(secs, start=1))
    for rec in records:
        if isinstance(rec, str):
            text = rec.strip()
        else:
            f, sec, a, b, z = rec
            text = f"{int(f)} {int(sec)} {_num(a)} {_num(b)} {_num(z)}"
        lines.append(f"   SITE_CHAR{suffix or ' '} {text}")
    return lines


# AERMETStage1's default surface QAOUT file, which AERMETStage3 reads when
# it is given no input names.
_STAGE1_QA_FILE = "stage1.qa"


@dataclass
class AERMETStage3:
    """
    AERMET Stage 2 (METPREP): merge the Stage 1 data and compute the
    boundary-layer parameters, writing AERMOD's ``.SFC`` and ``.PFL``.

    (pyaermod calls this ``Stage3`` for backward compatibility; AERMET
    calls it stage 2.)

    Inputs: the Stage 1 QAOUT files on the UPPERAIR, SURFACE and ONSITE
    pathways (``upper_air_qaout``, ``surface_qaout``, ``onsite_qaout``).
    When all three are None the deck names Stage 1's default upper-air and
    surface QAOUT files; :meth:`with_inputs_from` copies the names from an
    :class:`AERMETStage1`, and the pipeline does so automatically.

    Surface characteristics, in order of precedence:

    * ``aersurf_file``: an AERSURFACE output file (AERSURF keyword);
    * ``site_char``: SITE_CHAR records, each a string ``"f s albedo bowen z0"``
      or a tuple ``(f, s, albedo, bowen, z0)``, with ``frequency``
      (ANNUAL, SEASONAL or MONTHLY; default ANNUAL), ``num_sectors`` and
      ``sectors`` (``(start, end)`` degrees per sector; default one
      0-360 sector);
    * otherwise the 12 monthly ``albedo``, ``bowen`` and ``roughness``
      values for one 0-360 sector: FREQ_SECT ANNUAL when all months are
      equal, MONTHLY otherwise.

    ``methods`` are METHOD records such as ``("REFLEVEL", "SUBNWS")`` or
    ``("WIND_DIR", "RANDOM")``. ``nws_height`` is the NWS anemometer
    height (NWS_HGT WIND); it defaults to ``station.anemometer_height``.

    A deck with NWS surface data and no on-site data always gets
    ``METHOD REFLEVEL SUBNWS`` (added when ``methods`` has no REFLEVEL
    record): AERMET 26135 stops with E87 without it (mod_pbl.f90,
    A097_SUBNWS), as the AERMET user's guide says it should. SUBNWS with
    SURFACE data needs NWS_HGT (E72 otherwise), so such a deck raises
    ValueError when neither ``nws_height`` nor ``station`` is set.
    ``extra_lines`` are written verbatim at the end of METPREP.

    ``merge_file`` is kept for compatibility and ignored: METPREP's DATA
    keyword is obsolete (mod_read_input.f90 ignores it).
    """

    # Job control
    job_id: str = "STAGE3"
    messages: Optional[Union[int, str]] = None  # deprecated: see message_file

    # Input from Stage 2 (obsolete; ignored)
    merge_file: str = "stage2.mrg"

    # Site characteristics
    station: Optional[AERMETStation] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    time_zone: Optional[int] = None

    # Surface characteristics
    num_sectors: int = 1  # Number of wind direction sectors for surface characteristics
    site_char: List[SiteChar] = field(default_factory=list)  # SITE_CHAR records

    # Albedo, Bowen ratio, roughness length (12 months)
    albedo: List[float] = field(default_factory=lambda: [0.15] * 12)
    bowen: List[float] = field(default_factory=lambda: [1.0] * 12)
    roughness: List[float] = field(default_factory=lambda: [0.1] * 12)

    # Date range
    start_date: str = "2020/01/01"
    end_date: str = "2020/12/31"

    # Output files
    output_file: str = "stage3.out"  # REPORT
    surface_file: str = "aermod.sfc"  # OUTPUT
    profile_file: str = "aermod.pfl"  # PROFILE

    message_file: str = "stage3.msg"  # MESSAGES
    upper_air_qaout: Optional[str] = None
    surface_qaout: Optional[str] = None
    onsite_qaout: Optional[str] = None
    methods: List[Tuple[str, str]] = field(default_factory=list)
    nws_height: Optional[float] = None
    frequency: Optional[str] = None
    sectors: List[Tuple[float, float]] = field(default_factory=list)
    aersurf_file: Optional[str] = None
    secondary_site_char: List[SiteChar] = field(default_factory=list)  # SITE_CHAR2
    secondary_frequency: Optional[str] = None  # FREQ_SECT2
    secondary_num_sectors: int = 1
    secondary_sectors: List[Tuple[float, float]] = field(default_factory=list)  # SECTOR2
    secondary_aersurf_file: Optional[str] = None  # AERSURF2
    asos_1min_file: Optional[str] = None  # SURFACE ASOS1MIN (AERMINUTE output)
    extra_lines: List[str] = field(default_factory=list)

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
        for name in ("frequency", "secondary_frequency"):
            value = getattr(self, name)
            if value is not None and value.upper() not in FREQUENCIES:
                raise ValueError(
                    f"{name} must be one of {', '.join(FREQUENCIES)}, got {value!r}"
                )

    def with_inputs_from(self, stage1: AERMETStage1) -> "AERMETStage3":
        """A copy reading ``stage1``'s QAOUT files, unless this deck names its own.

        Only the pathways Stage 1 processes are named, so a run without
        upper air does not point METPREP at an upper-air file that does
        not exist.
        """
        if any(q is not None for q in (self.upper_air_qaout, self.surface_qaout, self.onsite_qaout)):
            return self
        return replace(
            self,
            upper_air_qaout=stage1.upper_air_qaout if stage1.has_upper_air else None,
            surface_qaout=stage1.qa_file if stage1.has_surface else None,
            onsite_qaout=stage1.onsite.qaout_file if stage1.onsite is not None else None,
        )

    def _inputs(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if all(q is None for q in (self.upper_air_qaout, self.surface_qaout, self.onsite_qaout)):
            return _derived_name(_STAGE1_QA_FILE, "ua"), _STAGE1_QA_FILE, None
        return self.upper_air_qaout, self.surface_qaout, self.onsite_qaout

    def _site_char_lines(self) -> List[str]:
        lines = []
        if self.aersurf_file:
            lines.append(f"   AERSURF    {_filename(self.aersurf_file)}")
        elif self.site_char:
            lines.extend(_site_char_block(
                "", self.frequency, self.num_sectors, self.sectors, self.site_char))
        else:
            if int(self.num_sectors) != 1:
                raise ValueError(
                    "the monthly albedo/bowen/roughness lists describe one 0-360 sector; "
                    "give site_char records and sectors for more sectors"
                )
            months = list(zip(self.albedo, self.bowen, self.roughness))
            if all(m == months[0] for m in months):
                freq, months = "ANNUAL", months[:1]
            else:
                freq = "MONTHLY"
            records: List[SiteChar] = [(i, 1, a, b, z) for i, (a, b, z) in enumerate(months, start=1)]
            lines.extend(_site_char_block("", freq, 1, [], records))

        # The secondary site (the NWS station when on-site data are the
        # primary): FREQ_SECT2, SECTOR2, SITE_CHAR2 or AERSURF2.
        if self.secondary_aersurf_file:
            lines.append(f"   AERSURF2   {_filename(self.secondary_aersurf_file)}")
        elif self.secondary_site_char:
            lines.extend(_site_char_block(
                "2", self.secondary_frequency, self.secondary_num_sectors,
                self.secondary_sectors, self.secondary_site_char))
        return lines

    def to_aermet_input(self) -> str:
        """Generate the AERMET METPREP (stage 2) runstream."""
        lines = []

        # Header
        lines.append("** AERMET Stage 3 Input (AERMET stage 2, METPREP)")
        lines.append(f"** Job: {self.job_id}")
        lines.append("**")

        lines.append("JOB")
        lines.append(f"   REPORT     {_filename(self.output_file)}")
        lines.append(f"   MESSAGES   {_filename(_messages_file(self.messages, self.message_file, 'AERMETStage3'))}")
        lines.append("")

        ua_qa, sf_qa, os_qa = self._inputs()
        if ua_qa:
            lines += ["UPPERAIR", f"   QAOUT      {_filename(ua_qa)}", ""]
        if sf_qa or self.asos_1min_file:
            lines.append("SURFACE")
            if sf_qa:
                lines.append(f"   QAOUT      {_filename(sf_qa)}")
            if self.asos_1min_file:
                lines.append(f"   ASOS1MIN   {_filename(self.asos_1min_file)}")
            lines.append("")
        if os_qa:
            lines += ["ONSITE", f"   QAOUT      {_filename(os_qa)}", ""]

        lines.append("METPREP")
        lines.append(f"   XDATES     {self.start_date} TO {self.end_date}")
        # LOCATION is only needed for on-site mixing heights without upper
        # air (pbl_test warns W70 otherwise and uses the station's own).
        if self.station:
            lines.append("   LOCATION   " + _location(
                self.station.station_id, self.station.latitude,
                self.station.longitude, -int(self.station.time_zone)))
        elif self.latitude is not None and self.longitude is not None and self.time_zone is not None:
            lines.append("   LOCATION   " + _location(
                "SITE", self.latitude, self.longitude, -int(self.time_zone)))
        methods = [(str(item).upper(), str(action).upper()) for item, action in self.methods]
        has_surface = bool(sf_qa or self.asos_1min_file)
        if has_surface and not os_qa and not any(item == "REFLEVEL" for item, _ in methods):
            # NWS data only: AERMET 26135 requires SUBNWS (E87, A097_SUBNWS).
            methods.insert(0, ("REFLEVEL", "SUBNWS"))
        for item, action in methods:
            lines.append(f"   METHOD     {item} {action}")
        nws = self.nws_height
        if nws is None and self.station is not None:
            nws = self.station.anemometer_height
        if nws is None and has_surface and ("REFLEVEL", "SUBNWS") in methods:
            raise ValueError(
                "METHOD REFLEVEL SUBNWS with SURFACE data needs the NWS anemometer height "
                "(AERMET error E72, NWS_HGT KEYWORD MISSING): set nws_height or station"
            )
        if nws is not None:
            lines.append(f"   NWS_HGT    WIND {_num(nws)}")
        lines.append(f"   OUTPUT     {_filename(self.surface_file)}")
        lines.append(f"   PROFILE    {_filename(self.profile_file)}")
        lines.extend(self._site_char_lines())
        lines.extend(f"   {extra}" for extra in self.extra_lines)
        lines.append("")

        return "\n".join(lines)


def write_aermet_runfile(stage: int, input_file: str, output_path: str = "."):
    """
    Create a shell script that runs AERMET on one runstream file.

    AERMET reads the runstream named on its command line (or ``aermet.inp``
    in the working directory); it does not read standard input. The script
    names the deck by its absolute path, resolved when the script is
    written, so it runs from any directory but only in this checkout.

    Args:
        stage: Stage label for the script's name and messages.
        input_file: Path to the runstream file.
        output_path: Directory AERMET runs in (its outputs land there).
    """
    deck = Path(input_file).resolve()
    script = f"""#!/bin/bash
# AERMET Stage {stage} Run Script

# Set paths
AERMET_EXE="aermet"
INPUT_FILE="{deck}"
OUTPUT_PATH="{output_path}"

# Create output directory
mkdir -p "$OUTPUT_PATH"

# Run AERMET: the runstream is its first argument
cd "$OUTPUT_PATH"
"$AERMET_EXE" "$INPUT_FILE" | tee aermet_stage{stage}.log

# AERMET exits 0 even when it fails; its own verdict is the banner.
if grep -q "AERMET FINISHED SUCCESSFULLY" aermet_stage{stage}.log; then
    echo "AERMET Stage {stage} complete"
else
    echo "AERMET Stage {stage} FAILED; see the REPORT and MESSAGES files" >&2
    exit 1
fi
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


# Example usage
if __name__ == "__main__":
    print("PyAERMOD AERMET Input Generator")
    print("=" * 70)
    print()

    # Example: Create Stage 3 input (most common use case)
    station = AERMETStation(
        station_id="94846",  # WBAN of Chicago O'Hare (KORD)
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
    print("To run AERMET's METPREP stage (after Stage 1):")
    print("  aermet aermet_stage3.inp")
    print()
    print("Output files:")
    print("  - aermod.sfc (surface parameters)")
    print("  - aermod.pfl (profile data)")
    print()

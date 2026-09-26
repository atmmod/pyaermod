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

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
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
    POINTCAP = "POINTCAP"
    POINTHOR = "POINTHOR"
    SWPOINT = "SWPOINT"
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
    TTRM = "TTRM"
    TTRM2 = "TTRM2"


#: MODELOPT tokens for each terrain type. coset.f knows only FLAT and
#: ELEV; ``FLAT ELEV`` together is how it spells "flat sources in elevated
#: terrain" (it sets FLATSRCS), so ELEVATED and FLATSRCS have no token of
#: their own. Writing ``ELEVATED`` was a fatal E203.
TERRAIN_MODELOPT_TOKENS = {
    "FLAT": ("FLAT",),
    "ELEVATED": ("ELEV",),
    "FLATSRCS": ("FLAT", "ELEV"),
}

#: NO2 methods that take the NO2STACK in-stack ratio; with any other
#: (ARM2, or none) the keyword is E600 in coset.f.
NO2STACK_METHODS = ("OLM", "PVMRM", "GRSM", "TTRM", "TTRM2")


#: Concentration units AERMOD accepts on the background keywords
#: (OZONEVAL, OZONEFIL, OZONUNIT, NOXVALUE, NOX_FILE, NOX_UNIT); anything
#: else is a fatal E203 in ``coset.f``.
BACKGROUND_UNITS = ("PPB", "PPM", "UG/M3")

#: Temporal-variation flags for ``O3VALUES`` and ``NOX_VALS``, with the
#: number of values each requires. Same table as EMISFACT (``coset.f``,
#: subroutines O3VALS and NOXVALS).
TEMPORAL_FLAG_COUNTS: Dict[str, int] = {
    "ANNUAL": 1, "SEASON": 4, "MONTH": 12, "HROFDY": 24, "WSPEED": 6,
    "SEASHR": 96, "HRDOW": 72, "HRDOW7": 168, "SHRDOW": 288,
    "SHRDOW7": 672, "MHRDOW": 864, "MHRDOW7": 2016,
}


def _num(value: float) -> str:
    """Shortest fixed/scientific rendering that reads back to itself."""
    return f"{value:.10g}"


@dataclass
class TemporalValues:
    """A background concentration that varies by season, month, hour...

    The runstream form is ``O3VALUES <flag> <values>`` or ``NOX_VALS
    <flag> <values>``; AERMOD accepts the values over as many lines as
    needed and requires exactly :data:`TEMPORAL_FLAG_COUNTS` of them.

    Parameters
    ----------
    flag : str
        One of the keys of :data:`TEMPORAL_FLAG_COUNTS`.
    values : list of float
        The values, in AERMOD's order for that flag.
    """
    flag: str
    values: List[float] = field(default_factory=list)


@dataclass
class BackgroundSpec:
    """One background-concentration specification.

    Used for the whole domain, or for one wind-direction sector when
    ``O3SECTOR`` / ``NOXSECTR`` is in effect. AERMOD lets an hourly file
    coexist with a value or a temporal profile (the latter substitutes
    for hours the file is missing), but refuses ``value`` together with
    ``varying``.

    Parameters
    ----------
    value : float, optional
        ``OZONEVAL`` / ``NOXVALUE`` constant.
    value_units : str, optional
        Units on that line (PPB, PPM, UG/M3); AERMOD's default is UG/M3.
    hourly_file : str, optional
        ``OZONEFIL`` / ``NOX_FILE`` path.
    file_units : str, optional
        Units field on the file line.
    file_format : str, optional
        Fortran read format on the file line, or ``FREE``.
    varying : TemporalValues, optional
        ``O3VALUES`` / ``NOX_VALS`` profile.
    """
    value: Optional[float] = None
    value_units: Optional[str] = None
    hourly_file: Optional[str] = None
    file_units: Optional[str] = None
    file_format: Optional[str] = None
    varying: Optional[TemporalValues] = None

    def is_empty(self) -> bool:
        return (self.value is None and self.hourly_file is None
                and self.varying is None)


@dataclass
class OzoneData:
    """
    Ozone data for NO2 chemistry options (CO pathway ozone keywords).

    ``ozone_file`` and ``uniform_value`` are the simplest ways to say
    "one file" or "one value"; the other fields express everything
    AERMOD's OZONEVAL / OZONEFIL / O3VALUES / O3SECTOR / OZONUNIT
    keywords can. :meth:`spec` returns the whole-domain part as a
    :class:`BackgroundSpec`.

    Parameters
    ----------
    ozone_file : str, optional
        Path to the hourly ozone file (``OZONEFIL``).
    uniform_value : float, optional
        Constant ozone concentration (``OZONEVAL``).
    sector_values : dict, optional
        Mapping of sector index to a constant ozone value
        (``OZONEVAL SECTn``); requires ``sectors``.
    uniform_units : str, optional
        Units field on the ``OZONEVAL`` line (PPB, PPM, UG/M3).
    ozone_file_units : str, optional
        Units field on the ``OZONEFIL`` line.
    ozone_file_format : str, optional
        Fortran read format on the ``OZONEFIL`` line, or ``FREE``.
    varying : TemporalValues, optional
        ``O3VALUES`` profile.
    sectors : list of float
        ``O3SECTOR`` starting directions, degrees, ascending, 2 to 6.
    by_sector : dict
        Sector index -> :class:`BackgroundSpec` for the sector forms of
        the three keywords.
    units : str, optional
        ``OZONUNIT``: units for the ``O3VALUES`` profiles.
    """
    ozone_file: Optional[str] = None
    uniform_value: Optional[float] = None
    sector_values: Optional[Dict[int, float]] = None
    uniform_units: Optional[str] = None
    ozone_file_units: Optional[str] = None
    ozone_file_format: Optional[str] = None
    varying: Optional[TemporalValues] = None
    sectors: List[float] = field(default_factory=list)
    by_sector: Dict[int, BackgroundSpec] = field(default_factory=dict)
    units: Optional[str] = None

    def spec(self) -> BackgroundSpec:
        """The whole-domain (no-sector) specification."""
        return BackgroundSpec(
            value=self.uniform_value, value_units=self.uniform_units,
            hourly_file=self.ozone_file, file_units=self.ozone_file_units,
            file_format=self.ozone_file_format, varying=self.varying,
        )


@dataclass
class NOxBackground(BackgroundSpec):
    """
    NOx background for GRSM (CO NOXVALUE / NOX_FILE / NOX_VALS / NOX_UNIT /
    NOXSECTR).

    The :class:`BackgroundSpec` fields carry the whole-domain form;
    ``sectors`` and ``by_sector`` carry the ``NOXSECTR`` form, in which
    every value/file/profile line names its sector. AERMOD treats
    ``NOXVALUE`` together with ``NOX_VALS`` as a fatal conflict (E605).

    Parameters
    ----------
    units : str, optional
        ``NOX_UNIT``: units for the ``NOX_VALS`` profiles.
    sectors : list of float
        ``NOXSECTR`` starting directions, degrees, ascending, 2 to 6.
    by_sector : dict
        Sector index -> :class:`BackgroundSpec`.
    """
    units: Optional[str] = None
    sectors: List[float] = field(default_factory=list)
    by_sector: Dict[int, BackgroundSpec] = field(default_factory=dict)


def _background_lines(spec: BackgroundSpec, keywords: Tuple[str, str, str],
                      sector: Optional[int] = None) -> List[str]:
    """Runstream lines for one :class:`BackgroundSpec`.

    ``keywords`` is the (value, file, profile) keyword triple, i.e.
    ``("OZONEVAL", "OZONEFIL", "O3VALUES")`` or its NOx counterpart.
    Field order follows ``coset.f``: ``[SECTn] value [units]``,
    ``[SECTn] file [units [format]]`` and ``[SECTn] flag values...``. A
    format without units would be read as units, so UG/M3 (AERMOD's
    default) is written in that case.
    """
    value_kw, file_kw, vals_kw = keywords
    tag = f"SECT{sector}  " if sector else ""
    lines: List[str] = []
    if spec.value is not None:
        line = f"   {value_kw}  {tag}{_num(spec.value)}"
        if spec.value_units:
            line += f"  {spec.value_units}"
        lines.append(line)
    if spec.hourly_file:
        line = f"   {file_kw}  {tag}{spec.hourly_file}"
        if spec.file_units or spec.file_format:
            line += f"  {spec.file_units or 'UG/M3'}"
        if spec.file_format:
            line += f"  {spec.file_format}"
        lines.append(line)
    if spec.varying is not None:
        values = spec.varying.values
        per_line = 12
        for start in range(0, max(len(values), 1), per_line):
            chunk = " ".join(_num(v) for v in values[start:start + per_line])
            lines.append(f"   {vals_kw}  {tag}{spec.varying.flag}  {chunk}".rstrip())
    return lines


def _ozone_lines(oz: OzoneData) -> List[str]:
    """CO-pathway ozone keywords for an :class:`OzoneData`."""
    lines: List[str] = []
    if oz.sectors:
        lines.append("   O3SECTOR  " + "  ".join(_num(d) for d in oz.sectors))
    if oz.units:
        lines.append(f"   OZONUNIT  {oz.units}")
    kw = ("OZONEVAL", "OZONEFIL", "O3VALUES")
    lines += _background_lines(oz.spec(), kw)
    for sector, spec in sorted(oz.by_sector.items()):
        lines += _background_lines(spec, kw, sector=sector)
    for sector, value in sorted((oz.sector_values or {}).items()):
        if sector not in oz.by_sector:
            lines.append(f"   OZONEVAL  SECT{sector}  {_num(value)}")
    return lines


def _nox_lines(nox: NOxBackground) -> List[str]:
    """CO-pathway NOx background keywords for a :class:`NOxBackground`."""
    lines: List[str] = []
    if nox.sectors:
        lines.append("   NOXSECTR  " + "  ".join(_num(d) for d in nox.sectors))
    if nox.units:
        lines.append(f"   NOX_UNIT  {nox.units}")
    kw = ("NOXVALUE", "NOX_FILE", "NOX_VALS")
    lines += _background_lines(nox, kw)
    for sector, spec in sorted(nox.by_sector.items()):
        lines += _background_lines(spec, kw, sector=sector)
    return lines


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
        NOx background file (GRSM only): shorthand for
        ``NOxBackground(hourly_file=...)``. Ignored when
        ``nox_background`` is set.
    nox_background : NOxBackground, optional
        The full NOx background specification (GRSM only).
    """
    method: ChemistryMethod = ChemistryMethod.ARM2
    ozone_data: Optional[OzoneData] = None
    default_no2_ratio: float = 0.5
    olm_groups: List[SourceGroupDefinition] = field(default_factory=list)
    nox_file: Optional[str] = None
    nox_background: Optional[NOxBackground] = None

    def effective_nox_background(self) -> Optional[NOxBackground]:
        """``nox_background``, or one built from the ``nox_file`` shorthand."""
        if self.nox_background is not None:
            return self.nox_background
        if self.nox_file:
            return NOxBackground(hourly_file=self.nox_file)
        return None


# ============================================================================
# RESTART AND MULTI-YEAR OPTIONS (CO SAVEFILE / INITFILE / MULTYEAR)
# ============================================================================

#: Filename AERMOD uses for a bare ``SAVEFILE`` or ``INITFILE`` (coset.f,
#: subroutines SAVEFL and INITFL).
DEFAULT_RESTART_FILE = "SAVE.FIL"


@dataclass
class SaveFile:
    """``CO SAVEFILE [savfil [dayinc [savfl2]]]``: periodic result save.

    Parameters
    ----------
    filename : str, optional
        Save file; ``None`` writes a bare ``SAVEFILE`` and AERMOD uses
        :data:`DEFAULT_RESTART_FILE`.
    day_increment : int, optional
        Days between saves (AERMOD's default is 1).
    alternate_filename : str, optional
        Second file to alternate saves with.
    """
    filename: Optional[str] = None
    day_increment: Optional[int] = None
    alternate_filename: Optional[str] = None


@dataclass
class InitFile:
    """``CO INITFILE [inifil]``: initialise results from a save file.

    ``filename=None`` writes a bare ``INITFILE`` and AERMOD reads
    :data:`DEFAULT_RESTART_FILE`.
    """
    filename: Optional[str] = None


@dataclass
class MultiYear:
    """``CO MULTYEAR [H6H] savfil [initfil]``: chain one-year runs.

    Each year's run saves its result arrays to ``save_file``; the next
    year's deck names that file as its ``init_file``. AERMOD accepts the
    keyword for PM10, PM2.5, NO2, SO2, LEAD and OTHER only, and refuses
    it together with SAVEFILE or INITFILE.

    Parameters
    ----------
    save_file : str
        This year's save file.
    init_file : str, optional
        The previous year's save file.
    h6h : bool
        Write the legacy ``H6H`` field. AERMOD no longer requires it and
        warns (W352) when it is present; kept so a deck that carries it
        round-trips.
    """
    save_file: str
    init_file: Optional[str] = None
    h6h: bool = False


# ============================================================================
# GAS DRY-DEPOSITION DEFAULTS (CO GASDEPDF)
# ============================================================================

@dataclass
class GasDepositionDefaults:
    """``CO GASDEPDF fo fseas2 fseas5 [refspe]``: gas deposition defaults.

    Parameters
    ----------
    reactivity : float
        Reactivity factor ``fo`` (Wesely).
    fseas2 : float
        Fraction of maximum green LAI for seasonal category 2.
    fseas5 : float
        Fraction of maximum green LAI for seasonal category 5.
    reference_species : str, optional
        Optional reference species field.
    """
    reactivity: float
    fseas2: float
    fseas5: float
    reference_species: Optional[str] = None


# ============================================================================
# CONTROL PATHWAY
# ============================================================================

@dataclass
class UrbanArea:
    """One ``CO URBANOPT`` line.

    Parameters
    ----------
    population : float
        Urban population (AERMOD rejects values below 100, E203).
    urban_id : str, optional
        Urban area ID; required by AERMOD when a deck defines more than
        one area, meaningless when it defines one.
    name : str, optional
        Descriptive name (free text without blanks).
    roughness : float, optional
        Urban surface roughness length in metres (default 1.0 in AERMOD).
    """
    population: float
    urban_id: Optional[str] = None
    name: Optional[str] = None
    roughness: Optional[float] = None


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

    # Urban/rural. URBANOPT takes ``population [name] [roughness]`` for a
    # single urban area (coset.f URBOPT); ``urban_option`` is the optional
    # descriptive name in field 2. (The multi-area ``URBANOPT id pop``
    # form needs several URBANOPT cards and is not modelled.)
    urban_option: Optional[str] = None  # Urban area name if urban
    urban_population: Optional[float] = None  # Required population for URBANOPT
    urban_roughness: Optional[float] = None  # Optional urban surface roughness, m
    # Every URBANOPT line of a deck (AERMOD allows several areas, each
    # with its own ID, and switches URBANOPT and URBANSRC to the ID-first
    # layout when there is more than one). When set, this is what the
    # writer emits; the three fields above describe the first area.
    urban_areas: List[UrbanArea] = field(default_factory=list)

    # Low wind options
    low_wind_option: Optional[str] = None  # e.g., "LOWWIND3"

    # Non-regulatory model options. AERMOD gates some source types and
    # features behind these: RLINEXT is rejected outright with
    # "Non-DFAULT ALPHA Option Required" unless ALPHA is present.
    alpha: bool = False
    beta: bool = False
    # PSDCREDIT: PSD increment-credit run. Sources are then grouped with
    # PSDGROUP (INCRCONS / RETRBASE / NONRBASE) and SRCGROUP is refused
    # (soset.f, E105); see SourcePathway.psd_groups.
    psd_credit: bool = False

    # MODELOPT options pyaermod has no field for (SCREEN, FASTALL,
    # NOCHKD, ...). The reader fills this with the tokens it did not
    # recognise so a deck keeps its options when rewritten; the writer
    # appends them to MODELOPT as given.
    extra_model_options: List[str] = field(default_factory=list)

    # ARMRATIO min max (coset.f ARM2_Ratios): the ARM2 ratio bounds; needs
    # ARM2 (E145), 0 < min <= max <= 1 (E380) and 0.5-0.9 under DFAULT.
    arm2_ratios: Optional[Tuple[float, float]] = None

    # AWMADWNW options (coset.f AWMA_DOWNWASH): one to five of STREAMLINE,
    # AWMAUEFF, AWMAUTURB, AWMAUTURBHX, AWMAENTRAIN; ALPHA required (E122),
    # STREAMLINE needs AWMAUTURB or AWMAUTURBHX (E126), AWMAUEFF conflicts
    # with ORD_DWNW's ORDUEFF (E124). Probe decks 24c-24e.
    awma_downwash: List[str] = field(default_factory=list)
    # ORD_DWNW options (coset.f ORD_DOWNWASH): one to three of ORDCAV,
    # ORDUEFF, ORDTURB; ALPHA required (E123).
    ord_downwash: List[str] = field(default_factory=list)

    # ARCFTOPT [airport]: aircraft plume-rise option (coset.f, after
    # MODELOPT, E140); SourcePathway.aircraft_sources names the sources.
    aircraft_option: bool = False
    airport_id: Optional[str] = None

    # RUNORNOT: False writes ``RUNORNOT NOT``, which makes AERMOD parse
    # and cross-check the deck without running the model.
    run_model: bool = True

    # CO EVENTFIL [evfile [SOCONT|DETAIL]] (coset.f EVNTFL): the main run
    # writes the event deck to ``eventfil``; ``eventfil_option`` is the
    # EVENTOUT the event deck then carries (AERMOD's default is DETAIL).
    eventfil: Optional[str] = None
    eventfil_option: Optional[str] = None

    # NO2 chemistry options
    chemistry: Optional[ChemistryOptions] = None

    # Gas dry-deposition defaults (CO GASDEPDF / GASDEPVD / GDSEASON /
    # GDLANUSE). AERMOD accepts these only with the ALPHA option, and
    # refuses GDSEASON/GDLANUSE alongside GASDEPVD.
    gas_deposition_defaults: Optional[GasDepositionDefaults] = None
    gas_deposition_velocity: Optional[float] = None  # GASDEPVD, m/s
    gas_deposition_seasons: Optional[List[int]] = None  # GDSEASON, 12 x 1-5
    gas_deposition_land_use: Optional[List[int]] = None  # GDLANUSE, 36 x 1-9

    # Restart and multi-year processing (CO SAVEFILE / INITFILE /
    # MULTYEAR). MULTYEAR excludes the other two.
    save_file: Optional[SaveFile] = None
    init_file: Optional[InitFile] = None
    multiyear: Optional[MultiYear] = None

    def to_aermod_input(self, event_processing: bool = False) -> str:
        """Generate AERMOD CO pathway text.

        ``event_processing`` writes the CO pathway of an EVENT deck:
        coset.f dispatches EVENTFIL, SAVEFILE, INITFILE and MULTYEAR
        only when the run is not an EVENT run (``.NOT.EVONLY``), so they
        are left off, as AERMOD leaves them off the event deck it writes.
        """
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

        # Add terrain type, spelled as coset.f reads it (ELEV, not ELEVATED)
        terrain = self.terrain_type.value if isinstance(self.terrain_type, TerrainType) else self.terrain_type
        model_opts.extend(TERRAIN_MODELOPT_TOKENS.get(str(terrain).upper(), (str(terrain),)))

        # Regulatory default mode
        if self.regulatory_default:
            model_opts.append("DFAULT")

        # Non-regulatory options, which AERMOD requires before it will
        # accept certain source types and keywords.
        if self.alpha:
            model_opts.append("ALPHA")
        if self.beta:
            model_opts.append("BETA")
        if self.psd_credit:
            model_opts.append("PSDCREDIT")

        # Append chemistry method to MODELOPT
        if self.chemistry is not None:
            model_opts.append(self.chemistry.method.value)

        # Options read from a deck that have no field of their own.
        for opt in self.extra_model_options:
            if opt.upper() not in model_opts:
                model_opts.append(opt.upper())

        lines.append(f"   MODELOPT  {' '.join(model_opts)}")

        # ARCFTOPT must follow MODELOPT (coset.f, E140)
        if self.aircraft_option:
            lines.append("   ARCFTOPT" + (f"  {self.airport_id}" if self.airport_id else ""))

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

        if self.urban_areas:
            # coset.f URBOPT: with one URBANOPT card the fields are
            # ``pop [name [z0]]``; with several, ``id pop [name [z0]]``.
            multi = len(self.urban_areas) > 1
            for area in self.urban_areas:
                fields = [area.urban_id] if multi and area.urban_id else []
                fields.append(f"{area.population:.1f}")
                if area.name or area.roughness is not None:
                    fields.append(area.name or "URBAN")
                if area.roughness is not None:
                    fields.append(f"{area.roughness:.2f}")
                lines.append("   URBANOPT  " + "  ".join(fields))
        elif self.urban_option or self.urban_population is not None:
            # Single-area URBANOPT: population [name] [roughness]. The
            # earlier "name population" order is the multi-area form,
            # which AERMOD reads as an illegal numeric field (E208) when
            # the deck has only one URBANOPT card.
            pop = self.urban_population if self.urban_population is not None else 1000000.0
            line = f"   URBANOPT  {pop:.1f}"
            if self.urban_option:
                line += f"  {self.urban_option}"
            if self.urban_roughness is not None:
                if not self.urban_option:
                    raise ValueError(
                        "urban_roughness needs urban_option: AERMOD reads the "
                        "roughness from the third URBANOPT field")
                line += f"  {self.urban_roughness:.2f}"
            lines.append(line)

        if self.low_wind_option:
            lines.append(f"   LOW_WIND  {self.low_wind_option}")

        # PRIME downwash research options (ALPHA)
        if self.awma_downwash:
            lines.append("   AWMADWNW  " + "  ".join(o.upper() for o in self.awma_downwash))
        if self.ord_downwash:
            lines.append("   ORD_DWNW  " + "  ".join(o.upper() for o in self.ord_downwash))

        # Gas dry-deposition defaults
        gdd = self.gas_deposition_defaults
        if gdd is not None:
            line = (f"   GASDEPDF  {_num(gdd.reactivity)}  {_num(gdd.fseas2)}"
                    f"  {_num(gdd.fseas5)}")
            if gdd.reference_species:
                line += f"  {gdd.reference_species}"
            lines.append(line)
        if self.gas_deposition_velocity is not None:
            lines.append(f"   GASDEPVD  {_num(self.gas_deposition_velocity)}")
        if self.gas_deposition_seasons:
            lines.append("   GDSEASON  " + "  ".join(
                str(int(v)) for v in self.gas_deposition_seasons))
        if self.gas_deposition_land_use:
            lines.append("   GDLANUSE  " + "  ".join(
                str(int(v)) for v in self.gas_deposition_land_use))

        # Chemistry-related CO keywords. The ozone keywords each have
        # one job in coset.f: OZONEVAL takes a constant, OZONEFIL a file,
        # O3VALUES a temporal flag and its values. (Earlier releases wrote
        # every form as O3VALUES, which AERMOD rejects as E201/E203.)
        if self.chemistry is not None:
            chem = self.chemistry
            if chem.ozone_data is not None:
                lines += _ozone_lines(chem.ozone_data)

            # NO2STACK (default in-stack ratio); ARM2 has no in-stack
            # ratio and rejects the keyword (E600).
            if chem.method.value in NO2STACK_METHODS:
                lines.append(f"   NO2STACK  {chem.default_no2_ratio:.4f}")

            # NOx background (GRSM)
            nox = chem.effective_nox_background()
            if nox is not None:
                lines += _nox_lines(nox)

        # ARM2 ratio bounds (needs the ARM2 option, E145 otherwise)
        if self.arm2_ratios is not None:
            lines.append(f"   ARMRATIO  {_num(self.arm2_ratios[0])}  {_num(self.arm2_ratios[1])}")

        # Restart / multi-year options (not dispatched in an EVENT run)
        if event_processing:
            pass
        elif self.multiyear is not None:
            my = self.multiyear
            line = "   MULTYEAR  " + ("H6H  " if my.h6h else "") + my.save_file
            if my.init_file:
                line += f"  {my.init_file}"
            lines.append(line)
        if self.save_file is not None and not event_processing:
            sf = self.save_file
            line = "   SAVEFILE"
            if sf.filename:
                line += f"  {sf.filename}"
                if sf.day_increment is not None or sf.alternate_filename:
                    # An alternate file sits in field 5, so field 4 must
                    # hold the increment; 1 is AERMOD's own default.
                    line += f"  {sf.day_increment if sf.day_increment is not None else 1}"
                if sf.alternate_filename:
                    line += f"  {sf.alternate_filename}"
            lines.append(line)
        if self.init_file is not None and not event_processing:
            line = "   INITFILE"
            if self.init_file.filename:
                line += f"  {self.init_file.filename}"
            lines.append(line)

        # Event file reference (the event deck itself never carries it)
        if self.eventfil and not event_processing:
            line = f"   EVENTFIL  {self.eventfil}"
            if self.eventfil_option:
                line += f"  {self.eventfil_option}"
            lines.append(line)

        # Run command
        lines.append(f"   RUNORNOT  {'RUN' if self.run_model else 'NOT'}")
        lines.append("CO FINISHED")

        return "\n".join(lines)


# ============================================================================
# METEOROLOGY PATHWAY
# ============================================================================

#: The nine turbulence-suppression keywords meset.f TURBOPT recognises
#: (one status switch for all of them: a second one is E135). Only the
#: first two may be combined with DFAULT (the others are reset with W444).
TURBULENCE_OPTIONS = (
    "NOTURB", "NOTURBST", "NOTURBCO", "NOSA", "NOSW",
    "NOSAST", "NOSWST", "NOSACO", "NOSWCO",
)

#: WINDCATS takes exactly this many upper bounds (meset.f WSCATS; any
#: other count reads as "no parameters", E200), each in 1-20 m/s and
#: increasing. AERMOD's defaults are 1.54, 3.09, 5.14, 8.23, 10.8.
WIND_CATEGORY_COUNT = 5

_DAYRANGE_FIELD_RE = re.compile(r"^(\d{1,3}(-\d{1,3})?|\d{1,2}/\d{1,2}(-\d{1,2}/\d{1,2})?)$")


def dayrange_field_is_valid(token: str) -> bool:
    """True for the four field forms meset.f DAYRNG reads: a Julian day
    (``50``), a Julian range (``50-60``), a month/day (``3/15``) or a
    month/day range (``3/15-4/30``)."""
    return bool(_DAYRANGE_FIELD_RE.match(token))


@dataclass
class ScimOptions:
    """``ME SCIMBYHR start interval [wetstart wetint] [sfcfile pflfile]``.

    Sampled Chronological Input Model: process hour ``start_hour`` of the
    first day and every ``interval``-th hour after it. meset.f SCIMIT
    dispatches the keyword only under ``MODELOPT SCIM`` and reads 4, 6 or
    8 fields; the wet-SCIM pair is no longer supported (W157, ignored)
    but is kept so EPA's ``scimtest`` deck round-trips, and a six-field
    card holds either that pair or the two summary files, told apart by
    non-numeric characters, which is how they are written back.

    Parameters
    ----------
    start_hour : int
        First hour sampled, 1-24 (E380).
    interval : int
        Hours between samples, at least 1 (E380); EPA uses 25.
    wet_start_hour, wet_interval : int, optional
        The obsolete wet-SCIM fields, written back if given.
    surface_summary_file, profile_summary_file : str, optional
        Files AERMOD writes the sampled surface and profile records to.
    """
    start_hour: int
    interval: int
    wet_start_hour: Optional[int] = None
    wet_interval: Optional[int] = None
    surface_summary_file: Optional[str] = None
    profile_summary_file: Optional[str] = None

    def to_aermod_fields(self) -> List[str]:
        fields = [str(int(self.start_hour)), str(int(self.interval))]
        if self.wet_start_hour is not None or self.wet_interval is not None:
            fields += [str(int(self.wet_start_hour or 0)), str(int(self.wet_interval or 0))]
        if self.surface_summary_file or self.profile_summary_file:
            fields += [self.surface_summary_file or "SCIM_SFC.DAT",
                       self.profile_summary_file or "SCIM_PFL.DAT"]
        return fields


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
    # meset.f STAEND takes six fields (dates) or eight (dates with an
    # hour after each date). Both hours must be set to write the latter.
    start_hour: Optional[int] = None
    end_hour: Optional[int] = None

    # Wind direction rotation
    wind_rotation: Optional[float] = None  # degrees

    # DAYRANGE fields as AERMOD reads them (meset.f DAYRNG): each a Julian
    # day, a Julian range, a month/day or a month/day range, accumulating
    # over any number of cards and written back on one. Not dispatched
    # under SCIM (E154) or in an EVENT run.
    day_ranges: List[str] = field(default_factory=list)
    # NUMYEARS n: years of meteorology, which sizes the MAXDCONT arrays
    # (meset.f NUMYR; exactly one integer field).
    num_years: Optional[int] = None
    # WINDCATS u1 u2 u3 u4 u5: the wind-speed category upper bounds
    # (meset.f WSCATS: exactly five, increasing, 1-20 m/s).
    wind_speed_categories: Optional[List[float]] = None
    # SCIMBYHR (see ScimOptions); needs MODELOPT SCIM.
    scim: Optional[ScimOptions] = None
    # One of TURBULENCE_OPTIONS, written as a bare keyword; the nine share
    # a status switch in meset.f so a deck carries at most one.
    turbulence_option: Optional[str] = None

    def to_aermod_input(self, event_processing: bool = False) -> str:
        """Generate AERMOD ME pathway text.

        ``event_processing`` writes the ME pathway of an EVENT deck, which
        meset.f reads without STARTEND (the events name their own dates;
        the keyword is dispatched only when ``.NOT.EVONLY``).
        """
        lines = ["ME STARTING"]

        # Surface and profile files
        lines.append(f"   SURFFILE  {self.surface_file}")
        lines.append(f"   PROFFILE  {self.profile_file}")

        # Station data (mandatory)
        lines.append(f"   SURFDATA  {self.surface_station_id}  {self.data_start_year}")
        lines.append(f"   UAIRDATA  {self.upper_air_station_id}  {self.data_start_year}")
        # One decimal, matching EPA's own decks. A profile base elevation
        # is metres MSL; sub-decimetre precision is not meaningful and
        # writing it would churn the golden reference deck.
        lines.append(f"   PROFBASE  {self.profile_base_elevation:.1f}  METERS")

        # Date range (if specified; not dispatched in an EVENT run)
        if not event_processing and all(
                x is not None for x in [self.start_year, self.start_month, self.start_day,
                                        self.end_year, self.end_month, self.end_day]):
            if self.start_hour is not None and self.end_hour is not None:
                lines.append(
                    f"   STARTEND  {self.start_year:4d} {self.start_month:2d} "
                    f"{self.start_day:2d} {self.start_hour:2d}  "
                    f"{self.end_year:4d} {self.end_month:2d} {self.end_day:2d} "
                    f"{self.end_hour:2d}"
                )
            else:
                lines.append(
                    f"   STARTEND  {self.start_year:4d} {self.start_month:2d} {self.start_day:2d}  "
                    f"{self.end_year:4d} {self.end_month:2d} {self.end_day:2d}"
                )

        if self.day_ranges and not event_processing:
            lines.append("   DAYRANGE  " + "  ".join(self.day_ranges))

        if self.scim is not None:
            lines.append("   SCIMBYHR  " + "  ".join(self.scim.to_aermod_fields()))

        # Wind rotation
        if self.wind_rotation is not None:
            lines.append(f"   WDROTATE  {self.wind_rotation:.2f}")

        if self.wind_speed_categories:
            lines.append("   WINDCATS  " + "  ".join(_num(v) for v in self.wind_speed_categories))

        if self.num_years is not None:
            lines.append(f"   NUMYEARS  {int(self.num_years)}")

        if self.turbulence_option:
            lines.append(f"   {self.turbulence_option.upper()}")

        lines.append("ME FINISHED")
        return "\n".join(lines)


# ============================================================================
# OUTPUT PATHWAY
# ============================================================================

def _plotfile_fields(averaging: str, source_group: str, filename: str) -> str:
    """PLOTFILE parameters for one averaging period.

    The period forms (PERIOD / ANNUAL) take no rank; the short-term
    forms take one. AERMOD counts fields, so an extra token is fatal
    rather than ignored.
    """
    if str(averaging).strip().upper() in ("PERIOD", "ANNUAL"):
        return f"{averaging}  {source_group}  {filename}"
    return f"{averaging}  {source_group}  FIRST  {filename}"


@dataclass
class MaxiFile:
    """``OU MAXIFILE aveper grpid thresh filnam [funit]``.

    Every value above ``threshold`` for one averaging period and source
    group is written to ``filename`` as it occurs. ouset.f (OUMXFL)
    counts fields: fewer than four data fields is fatal (E201), so there
    is no shorter form -- the one-field ``MAXIFILE filename`` pyaermod
    once wrote was rejected by every AERMOD release.

    Parameters
    ----------
    averaging_period : str
        One of the AVERTIME periods (``1``, ``24``, ... or ``MONTH``).
        PERIOD and ANNUAL averages have no threshold file.
    source_group : str
        Source group ID (``ALL`` or one defined with SRCGROUP).
    threshold : float
        Concentration above which a value is written.
    filename : str
        Output file.
    file_unit : int, optional
        Fortran unit number; AERMOD allocates one when omitted.
    """
    averaging_period: str
    source_group: str
    threshold: float
    filename: str
    file_unit: Optional[int] = None


@dataclass
class MaxDailyFile:
    """``OU MAXDAILY grpid filnam [funit]`` or ``OU MXDYBYYR ...``.

    MAXDAILY writes every day's maximum 1-hour value (24-hour value for
    PM2.5) at every receptor; MXDYBYYR writes each year's ranked daily
    maxima. AERMOD accepts both only for the 1-hour NO2/SO2 and 24-hour
    PM2.5 NAAQS processing, i.e. POLLUTID NO2/SO2 with AVERTIME 1, or
    PM25 with AVERTIME 24 (ouset.f, E162/E163).

    Parameters
    ----------
    source_group : str
        Source group ID (``ALL`` or one defined with SRCGROUP).
    filename : str
        Output file.
    file_unit : int, optional
        Fortran unit number; AERMOD allocates one when omitted.
    """
    source_group: str
    filename: str
    file_unit: Optional[int] = None


@dataclass
class MaxDailyContribution:
    """``OU MAXDCONT grpid upper lower filnam [funit]`` or
    ``OU MAXDCONT grpid upper THRESH thresh filnam [funit]``.

    Source-group contributions to the ranked daily maxima, from
    ``upper_rank`` down to ``lower_rank``, or down to the rank whose
    value first falls below ``threshold``. Exactly one of ``lower_rank``
    and ``threshold`` is given. RECTABLE must cover ``upper_rank``, and
    AERMOD refuses MAXDCONT together with SAVEFILE, INITFILE or
    MULTYEAR (E153).

    Parameters
    ----------
    source_group : str
        Source group whose contributions are wanted.
    upper_rank : int
        Highest rank (1 = the highest value) to analyse.
    filename : str
        Output file.
    lower_rank : int, optional
        Lowest rank to analyse, >= ``upper_rank``.
    threshold : float, optional
        Stop once the ranked value drops below this concentration.
    file_unit : int, optional
        Fortran unit number.
    """
    source_group: str
    upper_rank: int
    filename: str
    lower_rank: Optional[int] = None
    threshold: Optional[float] = None
    file_unit: Optional[int] = None

    def __post_init__(self) -> None:
        if (self.lower_rank is None) == (self.threshold is None):
            raise ValueError(
                "MaxDailyContribution takes exactly one of lower_rank "
                "(rank form) or threshold (THRESH form)"
            )


#: File types ``NOHEADER`` may name (ouset.f NOHEADER), besides ``ALL``.
#: Naming one the deck does not use is E164 at OUTQA.
NOHEADER_FILE_TYPES = (
    "MAXIFILE", "POSTFILE", "PLOTFILE", "SEASONHR", "RANKFILE",
    "MAXDAILY", "MXDYBYYR", "MAXDCONT",
)


def _resolve(filename: str, base_dir: Optional[Union[str, Path]]) -> Path:
    path = Path(filename)
    return path if path.is_absolute() or base_dir is None else Path(base_dir) / path


@dataclass
class RankFile:
    """``OU RANKFILE aveper rank filnam [funit]`` (ouset.f OURANK).

    The ``rank`` highest values for one averaging period across all
    receptors and groups, ranked; one card per averaging period (a second
    is E211) and the period must be on AVERTIME (E203). EPA's flatelev,
    lovett and mcr decks write one per short-term period.

    :meth:`read` returns the file through
    :func:`pyaermod.aermod_outputs.read_rankfile`.
    """
    averaging_period: str
    rank: int
    filename: str
    file_unit: Optional[int] = None

    def to_aermod_line(self) -> str:
        line = f"   RANKFILE  {self.averaging_period}  {int(self.rank)}  {self.filename}"
        if self.file_unit is not None:
            line += f"  {self.file_unit}"
        return line

    def read(self, base_dir: Optional[Union[str, Path]] = None):
        """The ranked values AERMOD wrote (``base_dir`` resolves a relative name)."""
        from .aermod_outputs import read_rankfile
        return read_rankfile(_resolve(self.filename, base_dir))


@dataclass
class SeasonHourFile:
    """``OU SEASONHR grpid filnam [funit]`` (ouset.f OUSEAS).

    Season-by-hour-of-day averages for one source group (one card per
    group, E211; the group must exist, E203). Refused under SCIM (E154).
    :meth:`read` returns it through
    :func:`pyaermod.aermod_outputs.read_seasonhr`.
    """
    source_group: str
    filename: str
    file_unit: Optional[int] = None

    def to_aermod_line(self) -> str:
        line = f"   SEASONHR  {self.source_group}  {self.filename}"
        if self.file_unit is not None:
            line += f"  {self.file_unit}"
        return line

    def read(self, base_dir: Optional[Union[str, Path]] = None):
        """The season-by-hour table AERMOD wrote."""
        from .aermod_outputs import read_seasonhr
        return read_seasonhr(_resolve(self.filename, base_dir))


@dataclass
class EvalFile:
    """``OU EVALFILE srcid filnam [funit]`` (ouset.f OUEVAL).

    The model-evaluation file for one source: arc maxima at the EVALCART
    receptor arcs. The source must exist (E203) and the deck needs
    EVALCART receptors (E256 at OUTQA; probe deck 28); EVALCART lines are
    kept in ``unparsed_lines`` and written back before the RE pathway
    ends. There is no reader for the file.
    """
    source_id: str
    filename: str
    file_unit: Optional[int] = None

    def to_aermod_line(self) -> str:
        line = f"   EVALFILE  {self.source_id}  {self.filename}"
        if self.file_unit is not None:
            line += f"  {self.file_unit}"
        return line


@dataclass
class ToxxFile:
    """``OU TOXXFILE aveper thresh filnam [funit]`` (ouset.f OUTOXX).

    Every value above ``threshold`` for one averaging period, for the
    TOXX post-processor; one card per period (E211), the period on
    AVERTIME (E203), and a warning (W296) for any period but 1 hour.
    AERMOD opens the file ``FORM='UNFORMATTED'``, so it is binary;
    :meth:`read` hands it to :func:`pyaermod.aermod_outputs.read_toxxfile`,
    which reads the text layout of the same records.
    """
    averaging_period: str
    threshold: float
    filename: str
    file_unit: Optional[int] = None

    def to_aermod_line(self) -> str:
        line = (f"   TOXXFILE  {self.averaging_period}  {_num(self.threshold)}  "
                f"{self.filename}")
        if self.file_unit is not None:
            line += f"  {self.file_unit}"
        return line

    def read(self, base_dir: Optional[Union[str, Path]] = None):
        """The threshold records, through :func:`read_toxxfile`."""
        from .aermod_outputs import read_toxxfile
        return read_toxxfile(_resolve(self.filename, base_dir))


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
    plot_file: Optional[str] = None
    # MAXIFILE threshold files, one per (averaging period, source group).
    # There is no filename-only form: see MaxiFile.
    maxi_files: List[MaxiFile] = field(default_factory=list)
    plot_file_averaging: str = "ANNUAL"  # Averaging period for default PLOTFILE

    # POSTFILE outputs
    postfile: Optional[str] = None  # Output file path
    postfile_averaging: Optional[str] = None  # e.g. "1" for 1-HR, "ANNUAL", etc.
    postfile_source_group: str = "ALL"
    postfile_format: str = "PLOT"  # PLOT (formatted) or UNFORM (unformatted/binary)

    # Per-group plot files: list of (averaging_period, source_group, filename)
    plot_file_groups: List[Tuple[str, str, str]] = field(default_factory=list)

    # Output type (CONC, DEPOS, DDEP, WDEP). Retained for callers that
    # set it, but AERMOD has no per-file output type: PLOTFILE and
    # POSTFILE take no such field, and writing one is a fatal "Too Many
    # Parameters" / "Invalid FORMAT". Which quantities are written is
    # decided by MODELOPT -- see ControlPathway.calculate_concentration,
    # .calculate_deposition, .calculate_dry_deposition and
    # .calculate_wet_deposition.
    output_type: str = "CONC"

    # FILEFORM: FIX (AERMOD's default) or EXP for exponential notation
    # in the plot/post/max files. None writes no FILEFORM line.
    file_format: Optional[str] = None

    # NOHEADER ALL, or one to eight of NOHEADER_FILE_TYPES: suppress the
    # header records of those output files (ouset.f NOHEADER). A type not
    # in use in the deck is E164.
    no_header: List[str] = field(default_factory=list)

    # The remaining OU file keywords, one entry per card.
    rank_files: List[RankFile] = field(default_factory=list)
    season_hour_files: List[SeasonHourFile] = field(default_factory=list)
    eval_files: List[EvalFile] = field(default_factory=list)
    toxx_files: List[ToxxFile] = field(default_factory=list)

    # EVENTOUT SOCONT|DETAIL: the one OU option of an EVENT deck besides
    # FILEFORM (evset.f EV_OUCARD). None lets the event deck writer use
    # ControlPathway.eventfil_option, then AERMOD's default DETAIL.
    event_output: Optional[str] = None

    # NAAQS design-value outputs (1-hour NO2/SO2, 24-hour PM2.5 only).
    max_daily_files: List[MaxDailyFile] = field(default_factory=list)
    max_daily_by_year_files: List[MaxDailyFile] = field(default_factory=list)
    max_daily_contributions: List[MaxDailyContribution] = field(
        default_factory=list)

    def to_aermod_input(self, event_processing: bool = False,
                        event_output: Optional[str] = None) -> str:
        """Generate AERMOD OU pathway text.

        ``event_processing`` writes the OU pathway of an EVENT deck, which
        evset.f EV_OUCARD reads: FILEFORM and EVENTOUT, nothing else (a
        RECTABLE there is E110). ``event_output`` overrides
        :attr:`event_output` for that line; with neither, AERMOD's own
        default ``DETAIL`` is written.
        """
        lines = ["OU STARTING"]

        # FILEFORM first: the POSTFILE header is written at setup with
        # whichever format is in force when the file is opened.
        if self.file_format:
            lines.append(f"   FILEFORM  {self.file_format}")

        if event_processing:
            option = event_output or self.event_output or "DETAIL"
            lines.append(f"   EVENTOUT  {option.upper()}")
            lines.append("OU FINISHED")
            return "\n".join(lines)

        if self.no_header:
            lines.append("   NOHEADER  " + "  ".join(t.upper() for t in self.no_header))
        if self.event_output:
            # Kept for a project read from an event deck and written as a
            # normal run; ouset.f has no EVENTOUT branch, so AERMOD would
            # reject it (E105), which is what the validator says.
            lines.append(f"   EVENTOUT  {self.event_output}")

        # Receptor table. A bare number on RECTABLE selects *only* that
        # rank -- "ALLAVE 10" is the tenth-highest alone, not the top ten
        # -- and a PLOTFILE asking for FIRST against it is then rejected
        # as an invalid HIVALU. The range form is what "top N" means.
        if self.receptor_table:
            rank = self.receptor_table_rank
            spec = "FIRST" if rank <= 1 else f"1-{rank}"
            lines.append(f"   RECTABLE  ALLAVE  {spec}")

        # Max table
        if self.max_table:
            lines.append(f"   MAXTABLE  ALLAVE  {self.max_table_rank}")

        # Day table
        if self.day_table:
            lines.append("   DAYTABLE  ALLAVE")

        # Summary file
        if self.summary_file:
            lines.append(f"   SUMMFILE  {self.summary_file}")

        # Threshold files: MAXIFILE aveper grpid thresh filnam [funit]
        for mf in self.maxi_files:
            line = (f"   MAXIFILE  {mf.averaging_period}  {mf.source_group}  "
                    f"{_num(mf.threshold)}  {mf.filename}")
            if mf.file_unit is not None:
                line += f"  {mf.file_unit}"
            lines.append(line)

        # Plot file. AERMOD's PLOTFILE syntax depends on the averaging
        # period and carries no output-type field:
        #   PLOTFILE PERIOD|ANNUAL grpid filename [unit]
        #   PLOTFILE <hours>       grpid rank filename [unit]
        # A rank on the period form, or an output type on either, is a
        # fatal "Too Many Parameters" (PERPLT/OUPLOT in AERMOD's ouset.f).
        if self.plot_file:
            lines.append(
                f"   PLOTFILE  {_plotfile_fields(self.plot_file_averaging, 'ALL', self.plot_file)}"
            )

        # Per-group plot files
        for avg_period, src_group, filename in self.plot_file_groups:
            lines.append(
                f"   PLOTFILE  {_plotfile_fields(avg_period, src_group, filename)}"
            )

        # Postfile:
        #   POSTFILE PERIOD|ANNUAL grpid format filename [unit]
        #   POSTFILE <hours>       grpid format filename [unit]
        # The format field is UNFORM or PLOT; anything else is rejected
        # as an invalid FORMAT parameter.
        if self.postfile:
            ave = self.postfile_averaging or "ANNUAL"
            lines.append(
                f"   POSTFILE  {ave}  {self.postfile_source_group}  "
                f"{self.postfile_format}  {self.postfile}"
            )

        lines.extend(rf.to_aermod_line() for rf in self.rank_files)
        lines.extend(sh.to_aermod_line() for sh in self.season_hour_files)
        lines.extend(ef.to_aermod_line() for ef in self.eval_files)
        lines.extend(tf.to_aermod_line() for tf in self.toxx_files)

        # NAAQS design-value files: MAXDAILY / MXDYBYYR take no averaging
        # period field (the period is implied by the pollutant); the
        # optional trailing field is the Fortran unit.
        for keyword, entries in (("MAXDAILY", self.max_daily_files),
                                 ("MXDYBYYR", self.max_daily_by_year_files)):
            for entry in entries:
                line = f"   {keyword}  {entry.source_group}  {entry.filename}"
                if entry.file_unit is not None:
                    line += f"  {entry.file_unit}"
                lines.append(line)
        for mdc in self.max_daily_contributions:
            bound = (f"THRESH  {_num(mdc.threshold)}" if mdc.threshold is not None
                     else str(mdc.lower_rank))
            line = (f"   MAXDCONT  {mdc.source_group}  {mdc.upper_rank}  {bound}"
                    f"  {mdc.filename}")
            if mdc.file_unit is not None:
                line += f"  {mdc.file_unit}"
            lines.append(line)

        lines.append("OU FINISHED")
        return "\n".join(lines)


# ============================================================================
# EVENT PATHWAY
# ============================================================================

#: ``EVENTOUT`` options (evset.f OEVENT): source contributions only, or
#: the detailed hourly output. Anything else is E203.
EVENT_OUTPUT_OPTIONS = ("SOCONT", "DETAIL")

#: Longest event name AERMOD holds (``EVNAME*10`` in modules.f; the names
#: it generates itself, ``H001H01001``, use all ten characters).
EVENT_NAME_LENGTH = 10


@dataclass
class EventLocation:
    """``EV EVENTLOC evname XR= x YR= y zelev [zhill [zflag]]``.

    The receptor of one event, in the layout evset.f EVLOC reads: the
    coordinate pair is introduced by ``XR=``/``YR=`` (Cartesian) or
    ``RNG=``/``DIR=`` (a range in metres and a direction in degrees,
    which AERMOD converts to x and y). The elevation is not optional --
    EVLOC wants at least eight fields on the card (E201 otherwise, probe
    deck 30) -- and the hill height and flagpole height follow it.

    Parameters
    ----------
    x, y : float
        Receptor coordinates, or range and direction when ``polar``.
    z_elev : float
        Terrain elevation of the receptor (m).
    z_hill : float
        Hill-height scale (m).
    z_flag : float, optional
        Flagpole receptor height (m); ``None`` leaves the field off.
    polar : bool
        Write ``RNG=``/``DIR=`` instead of ``XR=``/``YR=``.
    """
    x: float
    y: float
    z_elev: float = 0.0
    z_hill: float = 0.0
    z_flag: Optional[float] = None
    polar: bool = False

    def to_aermod_fields(self) -> str:
        """The fields after the event name, as AERMOD's MXEVNT writes them."""
        tags = ("RNG=", "DIR=") if self.polar else ("XR=", "YR=")
        text = (f"{tags[0]} {self.x:15.6f} {tags[1]} {self.y:15.6f} "
                f"{self.z_elev:10.4f} {self.z_hill:10.4f}")
        if self.z_flag is not None:
            text += f" {self.z_flag:10.4f}"
        return text


@dataclass
class EventPeriod:
    """``EV EVENTPER evname aveper grpid date conc``: one event.

    evset.f EVPER reads exactly five fields: the event name, the
    averaging period (one of the AVERTIME periods, 24 hours at most,
    E297), the source group, the date of the *end* of the period as
    ``YYMMDDHH``, and the concentration the main run found for it, which
    the event run checks its own result against. AERMOD writes the
    events it generates (``EVENTFIL``) in this form, one ``EVENTLOC``
    after each ``EVENTPER``.

    Parameters
    ----------
    event_name : str
        Up to :data:`EVENT_NAME_LENGTH` characters, unique in the deck.
    averaging_period : int
        Hours; must appear on ``AVERTIME``.
    date : str or int
        ``YYMMDDHH`` of the period's last hour.
    source_group : str
        A ``SRCGROUP`` ID (``ALL`` by default).
    original_conc : float
        The concentration the main run reported (0 when unknown).
    location : EventLocation, optional
        The receptor; every event needs one (E130).
    """
    event_name: str
    averaging_period: int
    date: Union[str, int]
    source_group: str = "ALL"
    original_conc: float = 0.0
    location: Optional[EventLocation] = None

    @property
    def date_text(self) -> str:
        """The date as the eight-digit field AERMOD reads."""
        return f"{int(self.date):08d}"

    def to_aermod_lines(self) -> List[str]:
        """The ``EVENTPER`` card and, when set, the ``EVENTLOC`` card."""
        name = f"{self.event_name:<{EVENT_NAME_LENGTH}}"
        lines = [
            f"   EVENTPER {name} {int(self.averaging_period):3d}  "
            f"{self.source_group:<8}   {self.date_text} {self.original_conc:17.5f}"
        ]
        if self.location is not None:
            lines.append(f"   EVENTLOC {name} {self.location.to_aermod_fields()}")
        return lines


@dataclass
class EventPathway:
    """
    AERMOD Event (EV) pathway.

    An EVENT run re-models specific averaging periods at specific
    receptors and reports each source's contribution. Its deck has the
    pathways ``CO SO ME EV OU`` -- no RE, and the EV block must come
    before OU (AERMOD's PRESET stops reading at ``OU FINISHED``, so an EV
    block after it is never seen, probe deck 30). The OU pathway of such
    a deck holds only ``EVENTOUT`` and ``FILEFORM``
    (:attr:`OutputPathway.event_output`, :attr:`OutputPathway.file_format`).
    :meth:`AERMODProject.to_aermod_input` writes that layout when
    ``event_processing`` is set, which the reader sets for any deck with
    an EV pathway; :meth:`AERMODProject.write` writes it to
    ``event_filename``.
    """
    events: List[EventPeriod] = field(default_factory=list)

    def add_event(self, event: EventPeriod):
        """Add an event period."""
        self.events.append(event)

    def to_aermod_input(self) -> str:
        """Generate AERMOD EV pathway text."""
        lines = ["EV STARTING"]
        for event in self.events:
            lines.extend(event.to_aermod_lines())
        lines.append("EV FINISHED")
        return "\n".join(lines)

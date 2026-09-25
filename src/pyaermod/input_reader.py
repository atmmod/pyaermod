"""
AERMOD ``.inp`` file reader.

Parses a textual AERMOD control-file back into an :class:`AERMODProject`
so a round-trip is possible:

    >>> project = read_aermod_input("facility.inp")
    >>> project.write("facility_clone.inp")

Supported pathway keywords (stored on the project model and written back):
    CO: TITLEONE, TITLETWO, MODELOPT (incl. OLM/PVMRM/ARM2/GRSM/TTRM/TTRM2,
        ALPHA/BETA, FLAT/ELEV and the FLAT ELEV pair, any other option
        kept in ``extra_model_options``), AVERTIME, POLLUTID, RUNORNOT,
        ELEVUNIT, FLAGPOLE, URBANOPT (one or several areas),
        LOW_WIND, HALFLIFE, DCAYCOEF, NO2STACK, OZONEVAL,
        OZONEFIL, O3VALUES, O3SECTOR, OZONUNIT, NOXVALUE, NOX_FILE,
        NOX_VALS, NOX_UNIT, NOXSECTR, GASDEPDF, GASDEPVD, GDSEASON,
        GDLANUSE, SAVEFILE, INITFILE, MULTYEAR, EVENTFIL (file only)
    SO: LOCATION (POINT/AREA/VOLUME/LINE/RLINE/RLINEXT/OPENPIT/AREACIRC/
        AREAPOLY/BUOYLINE), SRCPARAM, SRCGROUP, BACKGRND (value forms),
        BGSECTOR, GASDEPOS, PARTDIAM, MASSFRAX, PARTDENS, URBANSRC,
        BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ, AREAVERT, BLPINPUT,
        BLPGROUP
    RE: GRIDCART (XYINC or XPNTS/YPNTS, ELEV/HILL/FLAG rows), GRIDPOLR
        (ORIG by coordinates or source, DIST list, GDIR num/init/delta or
        DDIR list, ELEV/HILL/FLAG rows), DISCCART, ELEVUNIT
    ME: SURFFILE, PROFFILE, SURFDATA, UAIRDATA, PROFBASE, STARTEND (with
        or without hours), WDROTATE
    OU: RECTABLE, MAXTABLE, DAYTABLE, SUMMFILE, MAXIFILE, PLOTFILE,
        POSTFILE, FILEFORM, MAXDAILY, MXDYBYYR, MAXDCONT

Every other line -- a keyword with no field above, a form of a known
keyword the model cannot hold (a BACKGRND hourly file, a PLOTFILE with
a lower rank or a unit, a second POSTFILE, the definition lines of a
source type the reader does not construct), or an inline EV pathway --
is kept verbatim in :attr:`AERMODProject.unparsed_lines` (see
:mod:`pyaermod.unparsed`), reported through :mod:`logging` as one
warning per pathway and keyword, and written back into its pathway by
:meth:`AERMODProject.to_aermod_input` unless ``preserve_unparsed=False``.
Nothing is dropped silently, so a deck this reader does not fully
understand still opens and, rewritten, still carries every line; what it
does not do is produce byte-identical text.

Layout follows AERMOD's ``setup.f``: the first line of the deck fixes
the pathway column, the keyword occupies the eight columns after it, and
a line blank through the keyword columns continues the previous keyword
(``GRIDPOLR POL1 STA`` followed by ``POL1 DIST 100. 1000.``). The reader
is otherwise permissive about whitespace but strict about pathway order:
each pathway must appear once, inside ``XX STARTING`` and ``XX FINISHED``
markers.
"""
from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaPolySource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    BackgroundSpec,
    BuoyLineSegment,
    BuoyLineSource,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DiscreteReceptor,
    GasDepositionDefaults,
    GasDepositionParams,
    InitFile,
    LineSource,
    MaxDailyContribution,
    MaxDailyFile,
    MaxiFile,
    MeteorologyPathway,
    MultiYear,
    NOxBackground,
    OpenPitSource,
    OutputPathway,
    OzoneData,
    ParticleDepositionParams,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineExtSource,
    RLineSource,
    SaveFile,
    SourceGroupDefinition,
    SourcePathway,
    TemporalValues,
    TerrainType,
    UrbanArea,
    VolumeSource,
)
from .pathways import TEMPORAL_FLAG_COUNTS
from .unparsed import UnparsedLine, unparsed_summary

logger = logging.getLogger(__name__)

#: Leading digits of a rank token, so "8TH" reads as 8.
_LEADING_DIGITS_RE = re.compile(r"\d+")

#: Ordinal words AERMOD accepts for a RECTABLE rank, mapped to the rank.
_ORDINAL_WORDS = {
    "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5,
    "SIXTH": 6, "SEVENTH": 7, "EIGHTH": 8, "NINTH": 9, "TENTH": 10,
}

# ---------------------------------------------------------------------------
# Lexer / pathway splitter
# ---------------------------------------------------------------------------

PATHWAYS = ("CO", "SO", "RE", "ME", "OU", "EV")


@dataclass
class _Record:
    """One runstream line with its pathway/keyword columns resolved.

    ``fields`` are the data tokens as written (no ``N*V`` expansion),
    with a leading pathway code and the keyword removed; ``continuation``
    marks a line whose keyword columns were blank, so ``keyword`` was
    inherited from the previous record.
    """
    lineno: int
    keyword: str
    fields: List[str]
    raw: str
    continuation: bool = False


@dataclass
class _PathwayBlock:
    name: str
    lines: List[Tuple[int, str]] = field(default_factory=list)
    records: List[_Record] = field(default_factory=list)

    def record(self, lineno: int) -> _Record:
        for rec in self.records:
            if rec.lineno == lineno:
                return rec
        raise KeyError(lineno)


def _keyword_column(text: str) -> int:
    """0-based column where the pathway field starts.

    AERMOD (setup.f DEFINE) fixes the layout from the first line of the
    deck: the pathway field is the first non-blank column if that is one
    of columns 1-4, the keyword field is the eight columns starting three
    to its right, and the data fields begin twelve columns to its right.
    """
    for raw in text.splitlines():
        if raw.strip():
            indent = len(raw) - len(raw.lstrip())
            return indent if indent <= 3 else 0
    return 0


def _is_continuation(raw: str, locb: int, pathway: str) -> bool:
    """True when the keyword columns are blank (setup.f EXKEY inherits).

    The pathway columns may repeat the pathway code or be blank as well.
    A keyword written a column early (``' SUMMFILE'``) is *not* a
    continuation: AERMOD reads it as a pathway (E100), and pyaermod's
    tolerant tokenizer takes it as the keyword.
    """
    kw_field = raw[locb + 3:locb + 11]
    return kw_field.strip() == "" and raw[:locb + 3].strip().upper() in ("", pathway)


def _split_pathways(text: str) -> Dict[str, _PathwayBlock]:
    """Return a mapping of pathway name -> block.

    Raises ValueError on malformed input (missing STARTING/FINISHED,
    unknown pathway, etc.).
    """
    blocks: Dict[str, _PathwayBlock] = {}
    current: Optional[_PathwayBlock] = None
    locb = _keyword_column(text)
    prev_keyword: Optional[str] = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        # Skip blank lines + comment lines (** or ! prefix)
        if not line or line.startswith("**") or line.startswith("!"):
            continue

        tokens = line.split()
        if len(tokens) >= 2 and tokens[0] in PATHWAYS and tokens[1].upper() == "STARTING":
            if current is not None:
                raise ValueError(
                    f"line {lineno}: {tokens[0]} STARTING before previous "
                    f"{current.name} FINISHED"
                )
            current = _PathwayBlock(name=tokens[0])
            prev_keyword = None
            continue
        if len(tokens) >= 2 and tokens[0] in PATHWAYS and tokens[1].upper() == "FINISHED":
            if current is None or current.name != tokens[0]:
                raise ValueError(
                    f"line {lineno}: {tokens[0]} FINISHED without matching STARTING"
                )
            blocks[current.name] = current
            current = None
            continue

        if current is None:
            raise ValueError(
                f"line {lineno}: content outside any pathway block: {line!r}"
            )
        current.lines.append((lineno, line))

        # Resolve the keyword the way AERMOD does: strip a repeated
        # pathway code, then inherit the previous keyword when the
        # keyword columns are blank.
        toks = tokens
        if toks[0].upper() == current.name and len(toks) > 1:
            toks = toks[1:]
        continuation = (
            prev_keyword is not None
            and _is_continuation(raw.rstrip("\n"), locb, current.name)
        )
        if continuation:
            keyword, fields = prev_keyword, toks
        else:
            keyword, fields = toks[0].upper(), toks[1:]
        assert keyword is not None
        current.records.append(_Record(
            lineno=lineno, keyword=keyword, fields=fields,
            raw=raw.rstrip(), continuation=continuation,
        ))
        prev_keyword = keyword

    if current is not None:
        raise ValueError(f"{current.name} STARTING without FINISHED")

    return blocks


_REPEAT_RE = re.compile(r"^(\d+)\s*\*\s*(.+)$")


def _expand_shorthand(tokens: List[str]) -> List[str]:
    """Expand AERMOD ``N*VALUE`` tokens into repeated values.

    ``36*50.`` -> ``['50.', '50.', ...]`` (36 copies). Leaves tokens
    without the shorthand pattern unchanged.
    """
    out: List[str] = []
    for tok in tokens:
        m = _REPEAT_RE.match(tok)
        if m:
            n = int(m.group(1))
            val = m.group(2)
            out.extend([val] * n)
        else:
            out.append(tok)
    return out


def _group_keywords(block: _PathwayBlock) -> List[Tuple[str, List[str], int]]:
    """Return (keyword, tokens, lineno) tuples for a pathway block.

    Handles three AERMOD conventions inside a block:
    - Lines may start with the pathway code (e.g. ``SO BUILDHGT ...``);
      the prefix is stripped so the canonical keyword is the first
      output token.
    - A line whose keyword columns are blank continues the previous
      keyword (``GRIDPOLR POL1 STA`` followed by ``POL1 DIST ...``); the
      inherited keyword is reported.
    - Repeated values in shorthand form (``36*50.``) are expanded so
      downstream parsers see the full list.
    """
    return [
        (rec.keyword, _expand_shorthand(rec.fields), rec.lineno)
        for rec in block.records
    ]


def _drop(dropped: Optional[List[int]], lineno: int) -> None:
    """Record a line the parser could not represent structurally."""
    if dropped is not None:
        dropped.append(lineno)


# ---------------------------------------------------------------------------
# Pathway parsers
# ---------------------------------------------------------------------------

_CHEM_METHODS: Dict[str, ChemistryMethod] = {
    "OLM": ChemistryMethod.OLM,
    "PVMRM": ChemistryMethod.PVMRM,
    "ARM2": ChemistryMethod.ARM2,
    "GRSM": ChemistryMethod.GRSM,
    "TTRM": ChemistryMethod.TTRM,
    "TTRM2": ChemistryMethod.TTRM2,
}


_SECT_RE = re.compile(r"^SECT([1-6])$")


def _split_sector(toks: List[str]) -> Tuple[Optional[int], List[str]]:
    """Peel a leading ``SECTn`` token off a background keyword's fields."""
    if toks:
        m = _SECT_RE.match(toks[0].upper())
        if m:
            return int(m.group(1)), toks[1:]
    return None, toks


def _parse_background_keyword(
    kw: str, toks: List[str], specs: Dict[Optional[int], BackgroundSpec],
    *, value_kw: str, file_kw: str, vals_kw: str,
) -> None:
    """Fill ``specs`` from one OZONEVAL/OZONEFIL/O3VALUES-style line.

    ``specs`` is keyed by sector index (``None`` for the whole-domain
    form). Field layout per coset.f: ``[SECTn] value [units]``,
    ``[SECTn] file [units [format]]``, ``[SECTn] flag values...`` with the
    values of one flag accumulating over repeated lines.
    """
    sector, rest = _split_sector(toks)
    if not rest:
        return
    spec = specs.setdefault(sector, BackgroundSpec())
    if kw == value_kw:
        with contextlib.suppress(ValueError):
            spec.value = float(rest[0])
            if len(rest) > 1:
                spec.value_units = rest[1].upper()
    elif kw == file_kw:
        spec.hourly_file = rest[0]
        if len(rest) > 1:
            spec.file_units = rest[1].upper()
        if len(rest) > 2:
            spec.file_format = rest[2]
    elif kw == vals_kw:
        flag = rest[0].upper()
        try:
            values = [float(t) for t in rest[1:]]
        except ValueError:
            return
        if spec.varying is None or spec.varying.flag != flag:
            spec.varying = TemporalValues(flag=flag, values=[])
        spec.varying.values.extend(values)


def _parse_control(block: _PathwayBlock,
                   dropped: Optional[List[int]] = None) -> ControlPathway:
    title_one = title_two = ""
    avertime: List[str] = []
    pollutant = "OTHER"
    terrain = TerrainType.FLAT
    reg_default = False
    calc_conc = calc_dep = calc_ddep = calc_wdep = False
    half_life: Optional[float] = None
    decay: Optional[float] = None
    elev_units = "METERS"
    flagpole: Optional[float] = None
    urban: Optional[str] = None
    urban_pop: Optional[float] = None
    low_wind: Optional[str] = None
    alpha = beta = False
    saw_terrain = False
    extra_opts: List[str] = []
    urban_lines: List[List[str]] = []
    run_model = True
    eventfil: Optional[str] = None

    # Chemistry options (populated by NO2STACK, OZONEVAL, OZONEFIL, MODELOPT method)
    chem_method: Optional[ChemistryMethod] = None
    no2_ratio: Optional[float] = None
    o3_specs: Dict[Optional[int], BackgroundSpec] = {}
    o3_sectors: List[float] = []
    o3_units: Optional[str] = None
    nox_specs: Dict[Optional[int], BackgroundSpec] = {}
    nox_sectors: List[float] = []
    nox_units: Optional[str] = None
    o3_kw = dict(value_kw="OZONEVAL", file_kw="OZONEFIL", vals_kw="O3VALUES")
    nox_kw = dict(value_kw="NOXVALUE", file_kw="NOX_FILE", vals_kw="NOX_VALS")

    # Gas deposition defaults, restart and multi-year options
    gas_defaults: Optional[GasDepositionDefaults] = None
    gas_vd: Optional[float] = None
    gas_seasons: Optional[List[int]] = None
    gas_land_use: Optional[List[int]] = None
    save_file: Optional[SaveFile] = None
    init_file: Optional[InitFile] = None
    multiyear: Optional[MultiYear] = None

    for kw, toks, ln in _group_keywords(block):
        # Titles: join tokens with a single space, mirroring AERMOD's
        # free-form field parsing (leading/trailing/duplicate whitespace
        # is not significant). The writer normalizes identically
        # (pathways._normalize_title) so write -> read round-trips.
        if kw == "TITLEONE":
            title_one = " ".join(toks)
        elif kw == "TITLETWO":
            title_two = " ".join(toks)
        elif kw == "MODELOPT":
            for opt in toks:
                up = opt.upper()
                if up == "CONC":
                    calc_conc = True
                elif up == "DEPOS":
                    calc_dep = True
                elif up == "DDEP":
                    calc_ddep = True
                elif up == "WDEP":
                    calc_wdep = True
                elif up == "FLAT":
                    # coset.f MODOPT: FLAT after ELEV is ignored (W206);
                    # FLAT then ELEV means flat sources in elevated
                    # terrain (FLATSRCS).
                    if terrain == TerrainType.FLAT or not saw_terrain:
                        terrain = TerrainType.FLAT
                    saw_terrain = True
                elif up in ("ELEV", "ELEVATED"):
                    terrain = (TerrainType.FLATSRCS if saw_terrain and terrain == TerrainType.FLAT
                               else TerrainType.ELEVATED)
                    saw_terrain = True
                elif up == "FLATSRCS":
                    # pyaermod's own spelling (not an AERMOD token).
                    terrain = TerrainType.FLATSRCS
                    saw_terrain = True
                elif up == "DFAULT":
                    reg_default = True
                elif up in _CHEM_METHODS:
                    chem_method = _CHEM_METHODS[up]
                elif up == "ALPHA":
                    alpha = True
                elif up == "BETA":
                    beta = True
                else:
                    # SCREEN, FASTALL, PSDCREDIT, NOCHKD, ... have no
                    # field of their own; kept so the deck rewrites
                    # with the same options.
                    extra_opts.append(up)
        elif kw == "AVERTIME":
            avertime = [t.upper() for t in toks]
        elif kw == "POLLUTID":
            pollutant = toks[0].upper() if toks else "OTHER"
        elif kw == "RUNORNOT":
            run_model = not (toks and toks[0].upper() == "NOT")
        elif kw == "HALFLIFE":
            half_life = float(toks[0])
        elif kw == "DCAYCOEF":
            decay = float(toks[0])
        elif kw == "ELEVUNIT":
            elev_units = toks[0].upper() if toks else "METERS"
        elif kw == "FLAGPOLE":
            flagpole = float(toks[0]) if toks else None
        elif kw == "URBANOPT" and toks:
            urban_lines.append(toks)
        elif kw == "LOW_WIND":
            low_wind = toks[0] if toks else None
        elif kw == "NO2STACK" and toks:
            with contextlib.suppress(ValueError):
                no2_ratio = float(toks[0])
        elif kw == "EVENTFIL" and len(toks) == 1:
            eventfil = toks[0]
        elif kw == "O3VALUES" and toks and toks[0].upper() == "UNIFORM":
            # Not an AERMOD form (O3VALS rejects the flag, E203) but what
            # pyaermod < 2.1 wrote for a uniform value; read it as one.
            if len(toks) >= 2:
                with contextlib.suppress(ValueError):
                    o3_specs.setdefault(None, BackgroundSpec()).value = float(toks[1])
        elif kw == "O3VALUES" and len(toks) == 1 and toks[0].upper() not in TEMPORAL_FLAG_COUNTS:
            # Likewise the old file form; AERMOD wants OZONEFIL for a file.
            o3_specs.setdefault(None, BackgroundSpec()).hourly_file = toks[0]
        elif kw in ("OZONEVAL", "OZONEFIL", "O3VALUES"):
            _parse_background_keyword(kw, toks, o3_specs, **o3_kw)
        elif kw == "O3SECTOR":
            with contextlib.suppress(ValueError):
                o3_sectors = [float(t) for t in toks]
        elif kw == "OZONUNIT" and toks:
            o3_units = toks[0].upper()
        elif kw in ("NOXVALUE", "NOX_FILE", "NOX_VALS"):
            _parse_background_keyword(kw, toks, nox_specs, **nox_kw)
        elif kw == "NOXSECTR":
            with contextlib.suppress(ValueError):
                nox_sectors = [float(t) for t in toks]
        elif kw == "NOX_UNIT" and toks:
            nox_units = toks[0].upper()
        elif kw == "GASDEPDF" and len(toks) >= 3:
            # GASDEPDF fo fseas2 fseas5 [refspe]
            with contextlib.suppress(ValueError):
                gas_defaults = GasDepositionDefaults(
                    reactivity=float(toks[0]), fseas2=float(toks[1]),
                    fseas5=float(toks[2]),
                    reference_species=toks[3] if len(toks) > 3 else None,
                )
        elif kw == "GASDEPVD" and toks:
            with contextlib.suppress(ValueError):
                gas_vd = float(toks[0])
        elif kw == "GDSEASON" and toks:
            # 12 monthly Wesely season categories; N*V shorthand is
            # already expanded by _group_keywords.
            with contextlib.suppress(ValueError):
                gas_seasons = [int(float(t)) for t in toks]
        elif kw == "GDLANUSE" and toks:
            with contextlib.suppress(ValueError):
                gas_land_use = [int(float(t)) for t in toks]
        elif kw == "SAVEFILE":
            # SAVEFILE [savfil [dayinc [savfl2]]]; a bare keyword means
            # AERMOD's default SAVE.FIL, which is kept as filename=None.
            save_file = SaveFile(
                filename=toks[0] if toks else None,
                alternate_filename=toks[2] if len(toks) > 2 else None,
            )
            if len(toks) > 1:
                with contextlib.suppress(ValueError):
                    save_file.day_increment = round(float(toks[1]))
        elif kw == "INITFILE":
            init_file = InitFile(filename=toks[0] if toks else None)
        elif kw == "MULTYEAR":
            # MULTYEAR [H6H] savfil [initfil]; the H6H field is a
            # vestige AERMOD warns about but still accepts.
            h6h = bool(toks) and toks[0].upper() == "H6H"
            rest = toks[1:] if h6h else toks
            if rest:
                multiyear = MultiYear(
                    save_file=rest[0],
                    init_file=rest[1] if len(rest) > 1 else None,
                    h6h=h6h,
                )
        else:
            # ERRORFIL, DEBUGOPT, NO2EQUIL, ARMRATIO, an EVENTFIL with an
            # output option, ... : kept verbatim in unparsed_lines.
            _drop(dropped, ln)

    # URBANOPT: coset.f decides the field layout from the number of
    # cards (PREURB sets L_MULTURB when there is more than one):
    #   one card:   pop [name [z0]]
    #   several:    id pop [name [z0]]
    urban_areas: List[UrbanArea] = []
    multi_urban = len(urban_lines) > 1
    for fields in urban_lines:
        uid: Optional[str] = None
        rest = fields
        if multi_urban or (len(fields) > 1 and not _is_number(fields[0])
                           and _is_number(fields[1])):
            # ID first: the several-card layout, or the ``URBANOPT name
            # pop`` line pyaermod < 2.1 wrote for a single area (which
            # AERMOD rejects, E208; it is written back as pop name).
            uid, rest = fields[0], fields[1:]
        if not rest:
            continue
        try:
            population = float(rest[0])
        except ValueError:
            continue
        area = UrbanArea(population=population, urban_id=uid,
                         name=rest[1] if len(rest) > 1 else None)
        if len(rest) > 2:
            with contextlib.suppress(ValueError):
                area.roughness = float(rest[2])
        urban_areas.append(area)
    if urban_areas:
        urban = urban_areas[0].urban_id or urban_areas[0].name or "URBAN"
        urban_pop = urban_areas[0].population

    # Build ChemistryOptions if any chemistry-related keywords were found
    chemistry: Optional[ChemistryOptions] = None
    ozone_data: Optional[OzoneData] = None
    if o3_specs or o3_sectors or o3_units:
        whole = o3_specs.get(None, BackgroundSpec())
        by_sector = {k: v for k, v in o3_specs.items() if k is not None}
        ozone_data = OzoneData(
            ozone_file=whole.hourly_file,
            uniform_value=whole.value,
            uniform_units=whole.value_units,
            ozone_file_units=whole.file_units,
            ozone_file_format=whole.file_format,
            varying=whole.varying,
            sectors=o3_sectors,
            by_sector=by_sector,
            units=o3_units,
        )
    nox_background: Optional[NOxBackground] = None
    if nox_specs or nox_sectors or nox_units:
        whole = nox_specs.get(None, BackgroundSpec())
        nox_background = NOxBackground(
            value=whole.value, value_units=whole.value_units,
            hourly_file=whole.hourly_file, file_units=whole.file_units,
            file_format=whole.file_format, varying=whole.varying,
            units=nox_units, sectors=nox_sectors,
            by_sector={k: v for k, v in nox_specs.items() if k is not None},
        )
    if (chem_method is not None or no2_ratio is not None
            or ozone_data is not None or nox_background is not None):
        chemistry = ChemistryOptions(
            method=chem_method or ChemistryMethod.ARM2,
            ozone_data=ozone_data,
            default_no2_ratio=no2_ratio if no2_ratio is not None else 0.5,
            # nox_file mirrors the whole-domain NOX_FILE for callers that
            # only look at the shorthand (the validator's GRSM check).
            nox_file=nox_background.hourly_file if nox_background else None,
            nox_background=nox_background,
        )

    return ControlPathway(
        title_one=title_one,
        title_two=title_two or None,
        pollutant_id=_coerce_pollutant(pollutant),
        averaging_periods=avertime or ["ANNUAL"],
        terrain_type=terrain,
        calculate_concentration=calc_conc,
        calculate_deposition=calc_dep,
        calculate_dry_deposition=calc_ddep,
        calculate_wet_deposition=calc_wdep,
        regulatory_default=reg_default,
        half_life=half_life,
        decay_coefficient=decay,
        elevation_units=elev_units,
        flag_pole_height=flagpole,
        urban_option=urban,
        urban_population=urban_pop,
        urban_areas=urban_areas,
        low_wind_option=low_wind,
        alpha=alpha,
        beta=beta,
        extra_model_options=extra_opts,
        run_model=run_model,
        eventfil=eventfil,
        chemistry=chemistry,
        gas_deposition_defaults=gas_defaults,
        gas_deposition_velocity=gas_vd,
        gas_deposition_seasons=gas_seasons,
        gas_deposition_land_use=gas_land_use,
        save_file=save_file,
        init_file=init_file,
        multiyear=multiyear,
    )


def _is_number(tok: str) -> bool:
    try:
        float(tok)
    except ValueError:
        return False
    return True


def _coerce_pollutant(name: str) -> Union[PollutantType, str]:
    try:
        return PollutantType(name)
    except ValueError:
        return name


_BUILDING_KW_TO_FIELD = {
    "BUILDHGT": "building_height",
    "BUILDWID": "building_width",
    "BUILDLEN": "building_length",
    "XBADJ": "building_x_offset",
    "YBADJ": "building_y_offset",
}


def _parse_sources(block: _PathwayBlock,
                   dropped: Optional[List[int]] = None) -> SourcePathway:
    # LOCATION gives us each source's type and coordinates; SRCPARAM fills
    # in emission + physical parameters. Building-downwash keywords
    # (BUILDHGT, BUILDWID, ...) may appear on multiple lines per source
    # to cover 36 wind sectors; values accumulate in lists.
    locs: Dict[str, Dict[str, Any]] = {}
    src_types: Dict[str, str] = {}
    group_defs: List[SourceGroupDefinition] = []
    saw_group_keyword = False  # any SRCGROUP / PSDGROUP line
    saw_all_group = False      # a SRCGROUP ALL line, bare or with members

    # Deposition data accumulated by source ID before source objects exist
    gas_dep_data: Dict[str, GasDepositionParams] = {}
    part_dep_data: Dict[str, Dict[str, List[float]]] = {}  # srcid -> {diameters/fractions/densities}
    urbansrc_data: Dict[str, str] = {}  # srcid -> urban_area_name

    # Buoyant-line accumulation: BLPINPUT carries the group's averaged
    # geometry, BLPGROUP names the member line segments.
    blp_params: Dict[str, List[float]] = {}
    blp_groups: Dict[str, List[str]] = {}

    # Background concentration accumulation
    bg_uniform: Optional[float] = None
    bg_period_values: Dict[str, float] = {}
    bg_sectors: List[BackgroundSector] = []
    bg_sector_values: Dict[Tuple[int, str], float] = {}

    for kw, toks, ln in _group_keywords(block):
        if kw == "LOCATION":
            if len(toks) < 4:
                _drop(dropped, ln)
                continue
            sid, stype = toks[0], toks[1].upper()
            x, y = float(toks[2]), float(toks[3])
            src_types[sid] = stype
            locs.setdefault(sid, {})
            locs[sid].setdefault("_lines", []).append(ln)
            locs[sid]["x_coord"] = x
            locs[sid]["y_coord"] = y
            # LINE / RLINE / RLINEXT LOCATION format is:
            #   srcid TYPE x_start y_start x_end y_end [elev]  (LINE/RLINE)
            #   srcid TYPE x_start y_start z_start x_end y_end z_end (RLINEXT)
            # Non-LINE sources use the 5th token as base_elevation.
            if stype in ("LINE", "RLINE", "BUOYLINE") and len(toks) >= 6:
                locs[sid]["extra_loc"] = [float(toks[4]), float(toks[5])]
                if len(toks) > 6:
                    locs[sid]["z_elev"] = float(toks[6])
            elif stype == "RLINEXT" and len(toks) >= 8:
                locs[sid]["extra_loc"] = [
                    float(toks[4]), float(toks[5]),
                    float(toks[6]), float(toks[7]),
                ]
            else:
                # 5th token is base_elevation (float) or a keyword like
                # FLAT (marks source as flat-terrain per FLATSRCS option).
                if len(toks) > 4:
                    try:
                        locs[sid]["z_elev"] = float(toks[4])
                    except ValueError:
                        # Non-numeric (e.g. "FLAT") — store as flag,
                        # default elevation to 0.
                        locs[sid]["z_elev"] = 0.0
                        locs[sid]["_flat_source"] = True
                else:
                    locs[sid]["z_elev"] = 0.0
        elif kw == "SRCPARAM":
            if not toks:
                _drop(dropped, ln)
                continue
            sid = toks[0]
            params = [float(t) for t in toks[1:]]
            locs.setdefault(sid, {})["params"] = params
            locs[sid].setdefault("_lines", []).append(ln)
        elif kw in _BUILDING_KW_TO_FIELD:
            # Accumulate values across multiple BUILDHGT/WID/LEN/XBADJ/YBADJ lines
            if not toks:
                continue
            sid = toks[0]
            try:
                values = [float(t) for t in toks[1:]]
            except ValueError:
                continue
            field_name = _BUILDING_KW_TO_FIELD[kw]
            bucket = locs.setdefault(sid, {}).setdefault("_building", {})
            bucket.setdefault(field_name, []).extend(values)
            locs[sid].setdefault("_lines", []).append(ln)
        elif kw == "AREAVERT":
            # AREAVERT srcid x1 y1 x2 y2 ...  -- may repeat for one source,
            # six coordinate pairs to a line.
            if len(toks) < 3:
                continue
            sid = toks[0]
            try:
                values = [float(t) for t in toks[1:]]
            except ValueError:
                continue
            bucket = locs.setdefault(sid, {}).setdefault("_vertices", [])
            bucket.extend(
                (values[i], values[i + 1]) for i in range(0, len(values) - 1, 2)
            )
        elif kw == "BLPINPUT":
            # BLPINPUT [grpid] avg_line_len avg_bldg_hgt avg_bldg_wid
            #          avg_line_wid avg_bldg_sep avg_buoyancy
            # The group ID is optional; without it AERMOD files the
            # parameters under the implicit group "ALL".
            # Disambiguate on field count, as AERMOD does (IFC 8 vs 9 in
            # soset.f), not on whether the first token parses as a
            # number: a source group named "0" is legal and would
            # otherwise be eaten as the first parameter.
            if len(toks) >= 7:
                grp, rest = toks[0], toks[1:7]
            elif len(toks) == 6:
                grp, rest = "ALL", toks
            else:
                continue
            try:
                values = [float(t) for t in rest]
            except ValueError:
                continue
            blp_params[grp] = values[:6]
        elif kw == "BLPGROUP":
            if len(toks) < 2:
                continue
            blp_groups[toks[0]] = list(toks[1:])
        elif kw == "SRCGROUP":
            saw_group_keyword = True
            if not toks:
                _drop(dropped, ln)
                continue
            grp_name = toks[0]
            members = toks[1:]
            if grp_name.upper() == "ALL":
                saw_all_group = True
            # A bare "SRCGROUP ALL" is regenerated by the writer
            # (SourcePathway.include_all_group); it has no members to keep.
            if grp_name.upper() == "ALL" and not members:
                continue
            group_defs.append(SourceGroupDefinition(
                group_name=grp_name, member_source_ids=members,
            ))
        elif kw == "PSDGROUP":
            # PSD-credit runs group sources with PSDGROUP instead of
            # SRCGROUP; the line itself is kept verbatim (see unparsed).
            saw_group_keyword = True
            _drop(dropped, ln)

        # ------------------------------------------------------------------
        # Background concentration keywords
        # ------------------------------------------------------------------
        elif kw == "BACKGRND":
            # Forms:
            #   BACKGRND <uniform_value>
            #   BACKGRND <period> <value>
            #   BACKGRND SECT<n> <period> <value>
            #   BACKGRND <period> <filename>  (file-based, not stored structurally)
            if not toks:
                pass
            elif len(toks) == 1:
                with contextlib.suppress(ValueError):
                    bg_uniform = float(toks[0])
            elif toks[0].upper().startswith("SECT") and len(toks) >= 3:
                sect_str = toks[0].upper().lstrip("SECT")
                with contextlib.suppress(ValueError):
                    sect_id = int(sect_str)
                    value = float(toks[2])
                    bg_sector_values[(sect_id, toks[1].upper())] = value
            else:
                # "PERIOD VALUE" or "PERIOD FILENAME"
                try:
                    value = float(toks[1])
                    bg_period_values[toks[0].upper()] = value
                except (ValueError, IndexError):
                    # File-based background (BACKGRND HOURLY file): no
                    # structural field, kept verbatim.
                    _drop(dropped, ln)
        elif kw == "BGSECTOR":
            # BGSECTOR <dir1> <dir2> ...  — sector starting directions (degrees)
            for idx, tok in enumerate(toks, start=1):
                with contextlib.suppress(ValueError):
                    bg_sectors.append(BackgroundSector(
                        sector_id=idx, start_direction=float(tok)
                    ))
        elif kw == "BACKUNIT":
            _drop(dropped, ln)  # Recognized (PPB/UG/M3); no structural field

        # ------------------------------------------------------------------
        # Deposition keywords
        # ------------------------------------------------------------------
        elif kw == "GASDEPOS":
            # GASDEPOS srcid diffusivity alpha_r reactivity [henry_or_vd]
            if len(toks) < 4:
                continue
            sid = toks[0]
            try:
                diff = float(toks[1])
                alpha = float(toks[2])
                react = float(toks[3])
                last = float(toks[4]) if len(toks) > 4 else None
            except ValueError:
                continue
            gas_dep_data[sid] = GasDepositionParams(
                diffusivity=diff,
                alpha_r=alpha,
                reactivity=react,
                henry_constant=last,
            )
            locs.setdefault(sid, {}).setdefault("_lines", []).append(ln)
        elif kw == "PARTDIAM":
            # PARTDIAM srcid d1 d2 d3 ...
            if not toks:
                continue
            sid = toks[0]
            try:
                diameters = [float(t) for t in toks[1:]]
            except ValueError:
                continue
            part_dep_data.setdefault(sid, {})["diameters"] = diameters
            locs.setdefault(sid, {}).setdefault("_lines", []).append(ln)
        elif kw == "MASSFRAX":
            # MASSFRAX srcid f1 f2 f3 ...
            if not toks:
                continue
            sid = toks[0]
            try:
                fractions = [float(t) for t in toks[1:]]
            except ValueError:
                continue
            part_dep_data.setdefault(sid, {})["mass_fractions"] = fractions
            locs.setdefault(sid, {}).setdefault("_lines", []).append(ln)
        elif kw == "PARTDENS":
            # PARTDENS srcid r1 r2 r3 ...
            if not toks:
                continue
            sid = toks[0]
            try:
                densities = [float(t) for t in toks[1:]]
            except ValueError:
                continue
            part_dep_data.setdefault(sid, {})["densities"] = densities
            locs.setdefault(sid, {}).setdefault("_lines", []).append(ln)

        # ------------------------------------------------------------------
        # Urban source designation
        # ------------------------------------------------------------------
        elif kw == "URBANSRC":
            # URBANSRC srcid urban_area_name
            if len(toks) >= 2:
                urbansrc_data[toks[0]] = toks[1]
                locs.setdefault(toks[0], {}).setdefault("_lines", []).append(ln)
            else:
                _drop(dropped, ln)

        # ------------------------------------------------------------------
        # Everything else -- EMISFACT, HOUREMIS, INCLUDED, ELEVUNIT and
        # the keywords the reader has no branch for -- has no structural
        # field in SourcePathway and is kept verbatim in unparsed_lines.
        # ------------------------------------------------------------------
        else:
            _drop(dropped, ln)

    # Build source objects. The concrete type is chosen per LOCATION
    # keyword, so this list is deliberately heterogeneous.
    sources: List[Any] = []
    src: Any
    for sid, data in locs.items():
        if sid not in src_types:
            # SRCPARAM / building / deposition lines for a source this
            # deck defines elsewhere (an INCLUDED file) or a source-ID
            # range (PARTDIAM A-Z9999999): nothing to construct, so the
            # lines are kept verbatim where AERMOD will still read them.
            for lineno in data.get("_lines", []):
                _drop(dropped, lineno)
            continue
        stype = src_types[sid]
        params = data.get("params", [])
        common = dict(
            source_id=sid,
            x_coord=data.get("x_coord", 0.0),
            y_coord=data.get("y_coord", 0.0),
        )
        src = None
        if stype == "POINT":
            # SRCPARAM POINT: emission stackht stacktemp velocity diameter
            if len(params) < 5:
                continue
            src = PointSource(
                **common,
                emission_rate=params[0],
                stack_height=params[1],
                stack_temp=params[2],
                exit_velocity=params[3],
                stack_diameter=params[4],
            )
        elif stype == "AREA":
            # SRCPARAM AREA: emission relhgt xinit yinit [angle]
            if not params:
                continue
            src = AreaSource(
                **common,
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                initial_lateral_dimension=params[2] if len(params) > 2 else 10.0,
                initial_vertical_dimension=params[3] if len(params) > 3 else 10.0,
                angle=params[4] if len(params) > 4 else 0.0,
            )
        elif stype == "VOLUME":
            # SRCPARAM VOLUME: emission relhgt sylinit szinit
            if not params:
                continue
            src = VolumeSource(
                **common,
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                initial_lateral_dimension=params[2] if len(params) > 2 else 1.0,
                initial_vertical_dimension=params[3] if len(params) > 3 else 1.0,
            )
        elif stype == "LINE":
            # LOCATION LINE: x_start y_start x_end y_end [elev]
            # SRCPARAM:      emission release_height sy_init
            extra = data.get("extra_loc", [])
            if len(extra) < 2 or not params:
                # Treat as best-effort: require at least x_end,y_end
                continue
            src = LineSource(
                source_id=sid,
                x_start=common["x_coord"], y_start=common["y_coord"],
                x_end=extra[0], y_end=extra[1],
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                initial_lateral_dimension=params[2] if len(params) > 2 else 1.0,
            )
        elif stype == "RLINE":
            extra = data.get("extra_loc", [])
            if len(extra) < 2 or not params:
                continue
            src = RLineSource(
                source_id=sid,
                x_start=common["x_coord"], y_start=common["y_coord"],
                x_end=extra[0], y_end=extra[1],
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                initial_lateral_dimension=params[2] if len(params) > 2 else 3.0,
                initial_vertical_dimension=params[3] if len(params) > 3 else 1.5,
            )
        elif stype == "OPENPIT":
            # SRCPARAM: emission relhgt xinit yinit volume [angle]
            if len(params) < 5:
                continue
            src = OpenPitSource(
                **common,
                emission_rate=params[0],
                release_height=params[1],
                x_dimension=params[2],
                y_dimension=params[3],
                pit_volume=params[4],
                angle=params[5] if len(params) > 5 else 0.0,
            )
        elif stype == "AREACIRC":
            # SRCPARAM: emission relhgt radius [nverts]
            if not params:
                continue
            src = AreaCircSource(
                **common,
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                radius=params[2] if len(params) > 2 else 100.0,
                num_vertices=int(params[3]) if len(params) > 3 else 20,
            )
        elif stype == "AREAPOLY":
            # LOCATION is the polygon's first vertex; AREAVERT carries
            # the full ring. SRCPARAM: emission relhgt nverts [szinit]
            vertices = data.get("_vertices", [])
            if not params or len(vertices) < 3:
                continue
            src = AreaPolySource(
                source_id=sid,
                vertices=vertices,
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
            )
        elif stype == "RLINEXT":
            # LOCATION RLINEXT: x_start y_start z_start x_end y_end z_end,
            # so extra_loc holds (z_start, x_end, y_end, z_end).
            # SRCPARAM: emission dcl width init_sigma_z
            extra = data.get("extra_loc", [])
            if len(extra) < 4 or not params:
                continue
            src = RLineExtSource(
                source_id=sid,
                x_start=common["x_coord"], y_start=common["y_coord"],
                z_start=extra[0],
                x_end=extra[1], y_end=extra[2], z_end=extra[3],
                emission_rate=params[0],
                dcl=params[1] if len(params) > 1 else 0.0,
                road_width=params[2] if len(params) > 2 else 0.0,
                init_sigma_z=params[3] if len(params) > 3 else 0.0,
            )
        elif stype == "BUOYLINE":
            # Each BUOYLINE LOCATION is one *segment*; the source proper
            # is the BLPGROUP that names them, parameterised by BLPINPUT.
            # Segments are assembled after this loop, so nothing to build
            # here.
            continue

        if src is None:
            # A LOCATION type this reader does not construct (POINTCAP,
            # POINTHOR, SWPOINT, ...) or an incomplete definition: the
            # source's own lines are kept verbatim so the deck still
            # carries it.
            for lineno in data.get("_lines", []):
                _drop(dropped, lineno)
            logger.warning(
                "SO source %s (%s) is not modelled by pyaermod; its %d "
                "definition lines are kept verbatim in unparsed_lines",
                sid, stype, len(data.get("_lines", [])),
            )
            continue

        # Apply accumulated BUILDHGT/WID/LEN/XBADJ/YBADJ arrays, if any
        building = data.get("_building")
        if building:
            for attr, values in building.items():
                if hasattr(src, attr):
                    setattr(src, attr, values)

        # Apply gas deposition parameters
        if sid in gas_dep_data and hasattr(src, "gas_deposition"):
            src.gas_deposition = gas_dep_data[sid]

        # Apply particle deposition parameters
        if sid in part_dep_data and hasattr(src, "particle_deposition"):
            pd = part_dep_data[sid]
            src.particle_deposition = ParticleDepositionParams(
                diameters=pd.get("diameters", []),
                mass_fractions=pd.get("mass_fractions", []),
                densities=pd.get("densities", []),
            )

        # Apply URBANSRC designation
        if sid in urbansrc_data and hasattr(src, "is_urban"):
            src.is_urban = True
            src.urban_area_name = urbansrc_data[sid]

        sources.append(src)

    # Assemble buoyant-line sources. Each BUOYLINE LOCATION is a single
    # line segment; the source is the BLPGROUP naming them, carrying the
    # averaged geometry from its BLPINPUT record. A deck with one
    # buoyant line may omit both the BLPGROUP and the group ID on
    # BLPINPUT, in which case every BUOYLINE segment belongs to "ALL".
    buoyline_ids = [sid for sid, t in src_types.items() if t == "BUOYLINE"]
    if buoyline_ids:
        groups = blp_groups or {"ALL": buoyline_ids}
        for grp_id, member_ids in groups.items():
            avg = blp_params.get(grp_id) or blp_params.get("ALL")
            if avg is None:
                continue
            segments = []
            for member in member_ids:
                seg_data = locs.get(member)
                if seg_data is None:
                    continue
                extra = seg_data.get("extra_loc", [])
                seg_params = seg_data.get("params", [])
                if len(extra) < 2:
                    continue
                segments.append(BuoyLineSegment(
                    source_id=member,
                    x_start=seg_data.get("x_coord", 0.0),
                    y_start=seg_data.get("y_coord", 0.0),
                    x_end=extra[0], y_end=extra[1],
                    emission_rate=seg_params[0] if seg_params else 0.0,
                    release_height=(
                        seg_params[1] if len(seg_params) > 1 else 0.0
                    ),
                ))
            if not segments:
                continue
            sources.append(BuoyLineSource(
                source_id=grp_id,
                avg_line_length=avg[0],
                avg_building_height=avg[1],
                avg_building_width=avg[2],
                avg_line_width=avg[3],
                avg_building_separation=avg[4],
                avg_buoyancy_parameter=avg[5],
                line_segments=segments,
            ))

    # Build BackgroundConcentration if any BACKGRND keywords were found
    background: Optional[BackgroundConcentration] = None
    if bg_sectors and bg_sector_values:
        background = BackgroundConcentration(
            sectors=bg_sectors, sector_values=bg_sector_values,
        )
    elif bg_period_values:
        background = BackgroundConcentration(period_values=bg_period_values)
    elif bg_uniform is not None:
        background = BackgroundConcentration(uniform_value=bg_uniform)

    return SourcePathway(
        sources=sources, group_definitions=group_defs, background=background,
        # SRCGROUP ALL is written back when the deck had it, never when
        # the deck grouped its sources without it, and as the writer
        # sees fit when the deck defined no groups at all.
        include_all_group=(True if saw_all_group
                           else False if saw_group_keyword else None),
    )


#: Secondary keywords of the two receptor networks (reset.f RECART / REPOLR).
_CART_SUBKEYS = ("STA", "END", "XYINC", "XPNTS", "YPNTS", "ELEV", "HILL", "FLAG")
_POLR_SUBKEYS = ("STA", "END", "ORIG", "DIST", "GDIR", "DDIR", "ELEV", "HILL", "FLAG")


def _grid_record(
    toks: List[str], subkeys: Tuple[str, ...], current: Optional[str],
) -> Optional[Tuple[str, str, List[str]]]:
    """Split a GRIDCART/GRIDPOLR line into (network, sub-keyword, data).

    reset.f takes a bare sub-keyword in field 3 as belonging to the
    network being defined (``NETIDT = PNETID``), so ``GRIDPOLR DIST
    100. 200.`` and ``GRIDPOLR POL1 DIST 100. 200.`` are the same line.
    """
    if not toks:
        return None
    if toks[0].upper() in subkeys:
        if current is None:
            return None
        return current, toks[0].upper(), toks[1:]
    if len(toks) >= 2 and toks[1].upper() in subkeys:
        return toks[0], toks[1].upper(), toks[2:]
    return None


def _floats(toks: List[str]) -> Optional[List[float]]:
    try:
        return [float(t) for t in toks]
    except ValueError:
        return None


def _rows_to_lists(rows: Dict[int, List[float]]) -> Optional[List[List[float]]]:
    """``{row: values}`` (1-based rows, reset.f TERHGT) -> list of rows."""
    if not rows:
        return None
    return [rows.get(i, []) for i in range(1, max(rows) + 1)]


def _series_summary(values: List[float]) -> Tuple[float, int, float]:
    """(first, count, mean spacing) describing an explicit list.

    Fills the generator fields beside an explicit list so code that
    only reads ``x_init``/``x_num``/``x_delta`` (the GUI summary row)
    still sees the network's extent; the list itself is authoritative.
    """
    n = len(values)
    spacing = (values[-1] - values[0]) / (n - 1) if n > 1 else 0.0
    return values[0], n, spacing


def _parse_receptors(block: _PathwayBlock,
                     dropped: Optional[List[int]] = None) -> ReceptorPathway:
    carts: Dict[str, Dict[str, Any]] = {}
    polars: Dict[str, Dict[str, Any]] = {}
    discretes: List[DiscreteReceptor] = []
    elev_units = "METERS"
    current_cart: Optional[str] = None
    current_polar: Optional[str] = None

    for kw, toks, ln in _group_keywords(block):
        if kw == "ELEVUNIT":
            elev_units = toks[0].upper() if toks else "METERS"

        elif kw == "GRIDCART":
            rec = _grid_record(toks, _CART_SUBKEYS, current_cart)
            if rec is None:
                _drop(dropped, ln)
                continue
            name, sub, data = rec
            current_cart = name
            grid = carts.setdefault(name, {"grid_name": name, "rows": {}})
            if sub in ("STA", "END"):
                continue
            values = _floats(data)
            if sub == "XYINC":
                if values is None or len(values) < 6:
                    _drop(dropped, ln)
                    continue
                grid.update(
                    x_init=values[0], x_num=int(values[1]), x_delta=values[2],
                    y_init=values[3], y_num=int(values[4]), y_delta=values[5],
                )
            elif sub in ("XPNTS", "YPNTS"):
                # Explicit coordinate lists; reset.f XYPNTS accumulates
                # over repeated lines.
                if not values:
                    _drop(dropped, ln)
                    continue
                grid.setdefault("x_points" if sub == "XPNTS" else "y_points", []).extend(values)
            else:  # ELEV / HILL / FLAG: row index then values for that row
                if not values or len(values) < 2:
                    _drop(dropped, ln)
                    continue
                grid["rows"].setdefault(sub, {}).setdefault(int(values[0]), []).extend(values[1:])

        elif kw == "GRIDPOLR":
            rec = _grid_record(toks, _POLR_SUBKEYS, current_polar)
            if rec is None:
                _drop(dropped, ln)
                continue
            name, sub, data = rec
            current_polar = name
            grid = polars.setdefault(name, {"grid_name": name, "rows": {}})
            if sub in ("STA", "END"):
                continue
            values = _floats(data)
            if sub == "ORIG":
                # POLORG: two coordinates, or one source ID whose
                # location is the origin.
                if values is not None and len(values) == 2:
                    grid.update(x_origin=values[0], y_origin=values[1])
                elif len(data) == 1:
                    grid["origin_source_id"] = data[0]
                else:
                    _drop(dropped, ln)
            elif sub == "DIST":
                # POLDST: every field is a ring distance, however many.
                if not values:
                    _drop(dropped, ln)
                    continue
                grid.setdefault("distances", []).extend(values)
            elif sub == "GDIR":
                # GENPOL: exactly num, init, delta -- in that order.
                if values is None or len(values) != 3:
                    _drop(dropped, ln)
                    continue
                grid.update(dir_num=round(values[0]), dir_init=values[1],
                            dir_delta=values[2])
            elif sub == "DDIR":
                # RADRNG: an explicit direction list.
                if not values:
                    _drop(dropped, ln)
                    continue
                grid.setdefault("directions", []).extend(values)
            else:  # ELEV / HILL / FLAG: direction index then one value per ring
                if not values or len(values) < 2:
                    _drop(dropped, ln)
                    continue
                grid["rows"].setdefault(sub, {}).setdefault(int(values[0]), []).extend(values[1:])

        elif kw == "DISCCART":
            values = _floats(toks)
            if values is None or len(values) < 2:
                _drop(dropped, ln)
                continue
            z = values[2] if len(values) > 2 else 0.0
            z_hill = values[3] if len(values) > 3 else 0.0
            z_flag = values[4] if len(values) > 4 else 0.0
            discretes.append(DiscreteReceptor(
                x_coord=values[0], y_coord=values[1], z_elev=z,
                z_hill=z_hill, z_flag=z_flag,
            ))

        else:
            # EVALCART, DISCPOLR, INCLUDED and anything else: no
            # structural field in ReceptorPathway; kept verbatim.
            _drop(dropped, ln)

    cartesian_grids: List[CartesianGrid] = []
    for grid in carts.values():
        rows = grid.pop("rows")
        for sub, attr in (("ELEV", "grid_elevations"), ("HILL", "grid_hills"),
                          ("FLAG", "grid_flags")):
            if sub in rows:
                grid[attr] = _rows_to_lists(rows[sub])
        for axis in ("x", "y"):
            points = grid.get(f"{axis}_points")
            if points and f"{axis}_num" not in grid:
                init, num, delta = _series_summary(points)
                grid.update({f"{axis}_init": init, f"{axis}_num": num, f"{axis}_delta": delta})
            elif points and f"{axis}_num" in grid:
                # XYINC and XPNTS/YPNTS on one network is E180 in AERMOD;
                # the generator wins, matching what AERMOD had set first.
                grid.pop(f"{axis}_points")
        cartesian_grids.append(CartesianGrid(**grid))

    polar_grids: List[PolarGrid] = []
    for grid in polars.values():
        rows = grid.pop("rows")
        for sub, attr in (("ELEV", "elevations"), ("HILL", "hills"), ("FLAG", "flags")):
            if sub in rows:
                grid[attr] = _rows_to_lists(rows[sub])
        if grid.get("distances"):
            init, num, delta = _series_summary(grid["distances"])
            grid.update(dist_init=init, dist_num=num, dist_delta=delta)
        if grid.get("directions"):
            init, num, delta = _series_summary(grid["directions"])
            grid.update(dir_init=init, dir_num=num, dir_delta=delta)
        polar_grids.append(PolarGrid(**grid))

    return ReceptorPathway(
        cartesian_grids=cartesian_grids,
        polar_grids=polar_grids,
        discrete_receptors=discretes,
        elevation_units=elev_units,
    )


def _parse_meteorology(block: _PathwayBlock,
                       dropped: Optional[List[int]] = None) -> MeteorologyPathway:
    kw_map: Dict[str, Any] = {
        "surface_file": "",
        "profile_file": "",
        "surface_station_id": 0,
        "upper_air_station_id": 0,
        "data_start_year": 2020,
        "profile_base_elevation": 0.0,
    }
    dates: Dict[str, Any] = {}
    wind_rotation = None

    for kw, toks, ln in _group_keywords(block):
        if kw == "SURFFILE" and toks:
            kw_map["surface_file"] = toks[0]
        elif kw == "PROFFILE" and toks:
            kw_map["profile_file"] = toks[0]
        elif kw == "SURFDATA" and len(toks) >= 2:
            kw_map["surface_station_id"] = int(toks[0])
            kw_map["data_start_year"] = int(toks[1])
        elif kw == "UAIRDATA" and len(toks) >= 2:
            kw_map["upper_air_station_id"] = int(toks[0])
        elif kw == "PROFBASE" and toks:
            kw_map["profile_base_elevation"] = float(toks[0])
        elif kw == "STARTEND" and len(toks) in (6, 8):
            # meset.f STAEND: yr mo dy yr mo dy, or with an hour after
            # each date (eight fields).
            try:
                values = [int(float(t)) for t in toks]
            except ValueError:
                _drop(dropped, ln)
                continue
            if len(values) == 8:
                dates.update(
                    start_year=values[0], start_month=values[1], start_day=values[2],
                    start_hour=values[3], end_year=values[4], end_month=values[5],
                    end_day=values[6], end_hour=values[7],
                )
            else:
                dates.update(
                    start_year=values[0], start_month=values[1], start_day=values[2],
                    end_year=values[3], end_month=values[4], end_day=values[5],
                )
        elif kw == "WDROTATE" and toks:
            wind_rotation = float(toks[0])
        else:
            # SITEDATA, DAYRANGE, SCIMBYHR, NUMYEARS, WINDCATS, the
            # turbulence switches, ...: no structural field, kept verbatim.
            _drop(dropped, ln)

    return MeteorologyPathway(
        **kw_map, **dates,
        wind_rotation=wind_rotation,
    )


def _rank_value(tok: str) -> Optional[int]:
    """The rank a RECTABLE/PLOTFILE token names: 8, 8TH, EIGHTH -> 8."""
    up = tok.upper()
    if up in _ORDINAL_WORDS:
        return _ORDINAL_WORDS[up]
    digits = _LEADING_DIGITS_RE.match(up)
    return int(digits.group()) if digits else None


def _parse_output(block: _PathwayBlock,
                  dropped: Optional[List[int]] = None) -> OutputPathway:
    receptor_table = False
    max_table = False
    day_table = False
    rect_rank = 10
    max_rank = 10
    summary_file: Optional[str] = None
    maxi_files: List[MaxiFile] = []
    plot_file: Optional[str] = None
    plot_file_averaging = "ANNUAL"
    plot_file_groups: List[Tuple[str, str, str]] = []
    postfile: Optional[str] = None
    postfile_averaging: Optional[str] = None
    postfile_source_group = "ALL"
    postfile_format = "PLOT"
    file_format: Optional[str] = None
    max_daily: List[MaxDailyFile] = []
    max_daily_by_year: List[MaxDailyFile] = []
    max_daily_contributions: List[MaxDailyContribution] = []

    for kw, toks, ln in _group_keywords(block):
        if kw == "RECTABLE" and len(toks) >= 2:
            receptor_table = True
            # AERMOD accepts a bare rank ("8"), a numeric range ("1-10"),
            # or the ordinal-word forms ("FIRST", "FIRST-THIRD"). All are
            # represented here by their highest rank.
            rank_tok = toks[1].upper()
            if "-" in rank_tok:
                rank_tok = rank_tok.rsplit("-", 1)[-1]
            if rank_tok in _ORDINAL_WORDS:
                rect_rank = _ORDINAL_WORDS[rank_tok]
            else:
                # "8TH" and "8" both mean rank 8.
                digits = _LEADING_DIGITS_RE.match(rank_tok)
                if digits:
                    rect_rank = int(digits.group())
        elif kw == "MAXTABLE" and len(toks) >= 2:
            max_table = True
            with contextlib.suppress(ValueError):
                max_rank = int(toks[1])
        elif kw == "DAYTABLE":
            day_table = True
        elif kw == "SUMMFILE" and toks:
            summary_file = toks[0]
        elif kw == "MAXIFILE" and len(toks) >= 4:
            # MAXIFILE <aveper> <grpid> <thresh> <filename> [unit]
            # (ouset.f OUMXFL: fields 3-6, optional 7).
            try:
                maxi = MaxiFile(
                    averaging_period=toks[0].upper(), source_group=toks[1],
                    threshold=float(toks[2]), filename=toks[3],
                )
                if len(toks) > 4:
                    maxi.file_unit = int(float(toks[4]))
            except ValueError:
                _drop(dropped, ln)
                continue
            maxi_files.append(maxi)
        elif kw == "PLOTFILE":
            # PLOTFILE PERIOD|ANNUAL <group> <filename> [unit]
            # PLOTFILE <hours>       <group> <rank> <filename> [unit]
            # The period forms carry no rank, so the filename is one
            # field earlier; taking a fixed position reads the rank as
            # the filename.
            # The model holds no rank and no unit: a short-term line
            # whose rank is not the highest value, or any line with a
            # trailing unit, is kept verbatim instead.
            if len(toks) >= 3:
                period, group = toks[0], toks[1]
                is_period = period.strip().upper() in ("PERIOD", "ANNUAL")
                fname = toks[2] if is_period else (
                    toks[3] if len(toks) >= 4 else None
                )
                rank_ok = is_period or _rank_value(toks[2]) == 1
                expected = 3 if is_period else 4
                if fname is None or not rank_ok or len(toks) != expected:
                    _drop(dropped, ln)
                    continue
                if group.upper() == "ALL" and plot_file is None:
                    plot_file = fname
                    plot_file_averaging = period
                else:
                    plot_file_groups.append((period, group, fname))
            else:
                _drop(dropped, ln)
        elif kw == "POSTFILE" and len(toks) >= 4 and postfile is None:
            # POSTFILE <avg_period> <group> <format> <filename> [unit]
            # OutputPathway models one POSTFILE; further lines (one per
            # source group, as EPA's decks write them) are kept verbatim.
            postfile_averaging = toks[0]
            postfile_source_group = toks[1]
            postfile_format = toks[2].upper()
            postfile = toks[3]
            if len(toks) > 4:
                _drop(dropped, ln)  # a unit field the model has no place for
                postfile = None
                postfile_averaging = None
                postfile_source_group = "ALL"
                postfile_format = "PLOT"
        elif kw == "FILEFORM" and toks:
            file_format = toks[0].upper()
        elif kw in ("MAXDAILY", "MXDYBYYR") and len(toks) >= 2:
            # MAXDAILY <group> <filename> [unit] -- no averaging period
            # field; ouset.f reads the group from field 3.
            entry = MaxDailyFile(source_group=toks[0], filename=toks[1])
            if len(toks) > 2:
                with contextlib.suppress(ValueError):
                    entry.file_unit = int(float(toks[2]))
            (max_daily if kw == "MAXDAILY" else max_daily_by_year).append(entry)
        elif kw == "MAXDCONT" and len(toks) >= 4:
            # MAXDCONT <group> <upper> <lower> <filename> [unit]
            # MAXDCONT <group> <upper> THRESH <thresh> <filename> [unit]
            try:
                upper = int(float(toks[1]))
                if toks[2].upper() == "THRESH":
                    if len(toks) < 5:
                        continue
                    contribution = MaxDailyContribution(
                        source_group=toks[0], upper_rank=upper,
                        filename=toks[4], threshold=float(toks[3]),
                    )
                    unit_tok = toks[5] if len(toks) > 5 else None
                else:
                    contribution = MaxDailyContribution(
                        source_group=toks[0], upper_rank=upper,
                        filename=toks[3], lower_rank=int(float(toks[2])),
                    )
                    unit_tok = toks[4] if len(toks) > 4 else None
                if unit_tok is not None:
                    contribution.file_unit = int(float(unit_tok))
            except ValueError:
                _drop(dropped, ln)
                continue
            max_daily_contributions.append(contribution)
        else:
            # RANKFILE, SEASONHR, TOXXFILE, EVALFILE, NOHEADER, a short
            # or malformed line of a known keyword, ...: kept verbatim.
            _drop(dropped, ln)

    return OutputPathway(
        receptor_table=receptor_table,
        receptor_table_rank=rect_rank,
        max_table=max_table,
        max_table_rank=max_rank,
        day_table=day_table,
        summary_file=summary_file,
        maxi_files=maxi_files,
        plot_file=plot_file,
        plot_file_averaging=plot_file_averaging,
        plot_file_groups=plot_file_groups,
        postfile=postfile,
        postfile_averaging=postfile_averaging,
        postfile_source_group=postfile_source_group,
        postfile_format=postfile_format,
        file_format=file_format,
        max_daily_files=max_daily,
        max_daily_by_year_files=max_daily_by_year,
        max_daily_contributions=max_daily_contributions,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_aermod_input(text: str) -> AERMODProject:
    """Parse the text of an AERMOD ``.inp`` file into an AERMODProject.

    Every line the pathway parsers cannot represent on the model is
    returned in :attr:`AERMODProject.unparsed_lines` (see
    :mod:`pyaermod.unparsed`) and summarised in one warning per pathway
    and keyword through :mod:`logging`; nothing is dropped silently.
    """
    blocks = _split_pathways(text)

    for required in ("CO", "SO", "RE", "ME"):
        if required not in blocks:
            raise ValueError(f"AERMOD input is missing required pathway {required}")

    dropped: Dict[str, List[int]] = {code: [] for code in PATHWAYS}
    control = _parse_control(blocks["CO"], dropped["CO"])
    sources = _parse_sources(blocks["SO"], dropped["SO"])
    receptors = _parse_receptors(blocks["RE"], dropped["RE"])
    meteorology = _parse_meteorology(blocks["ME"], dropped["ME"])
    output = _parse_output(blocks.get("OU", _PathwayBlock("OU")), dropped["OU"])
    if "EV" in blocks:
        # An inline EV pathway has no model at all; keep it whole.
        dropped["EV"] = [rec.lineno for rec in blocks["EV"].records]

    unparsed: List[UnparsedLine] = []
    for code, linenos in dropped.items():
        block = blocks.get(code)
        if block is None:
            continue
        for lineno in sorted(set(linenos)):
            rec = block.record(lineno)
            unparsed.append(UnparsedLine(
                pathway=code, keyword=rec.keyword, fields=list(rec.fields),
                lineno=lineno, raw=rec.raw,
            ))
    unparsed.sort(key=lambda u: u.lineno)
    for (code, keyword), count in unparsed_summary(unparsed).items():
        logger.warning(
            "%s %s: %d line%s not modelled by pyaermod; kept verbatim in "
            "AERMODProject.unparsed_lines and written back on output",
            code, keyword, count, "" if count == 1 else "s",
        )

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output,
        unparsed_lines=unparsed,
    )


def read_aermod_input(
    path: Union[str, Path],
    *,
    sandbox: bool = False,
) -> AERMODProject:
    """Read an AERMOD ``.inp`` file from disk and return the project.

    Parameters
    ----------
    path : str or Path
        Path to the .inp file.
    sandbox : bool, default False
        If True, validate that every absolute path referenced inside
        the .inp (SURFFILE, PROFFILE, OZONEFIL, etc.) and every
        resolved relative path stays inside the .inp's parent directory.
        Raises :class:`PathTraversalError` on the first escape. Use this
        when ingesting untrusted .inp files (third-party permits,
        forwarded drafts) before passing the project to AERMOD.

        The default (False) preserves prior behavior: paths are stored
        as-is and AERMOD itself decides what to open at run time.
    """
    p = Path(path).resolve()
    project = parse_aermod_input(p.read_text(encoding="utf-8"))
    if sandbox:
        _validate_paths_within(project, base=p.parent)
    return project


class PathTraversalError(ValueError):
    """Raised when a sandboxed .inp references a path outside its base dir."""


def _validate_paths_within(project: AERMODProject, base: Path) -> None:
    """Reject project paths that escape `base`.

    Inspects fields known to carry filenames or paths users might
    accept from untrusted sources:

    - meteorology.surface_file / profile_file
    - control.chemistry.ozone_data.ozone_file (if chemistry is set)
    - control.chemistry.nox_file
    - output.summary_file / plot_file / postfile / maxi_files
    - output.plot_file_groups (per-group filenames)
    """
    base = base.resolve()

    def _check(label: str, raw: Optional[str]) -> None:
        if not raw:
            return
        candidate = Path(raw)
        full = (candidate if candidate.is_absolute() else base / candidate).resolve()
        try:
            full.relative_to(base)
        except ValueError:
            raise PathTraversalError(
                f"{label} resolves to {full} which is outside the sandbox "
                f"root {base}. If this is intentional, pass sandbox=False."
            ) from None

    met = project.meteorology
    _check("meteorology.surface_file", getattr(met, "surface_file", None))
    _check("meteorology.profile_file", getattr(met, "profile_file", None))

    control = project.control
    chem = getattr(control, "chemistry", None)
    if chem is not None:
        oz = getattr(chem, "ozone_data", None)
        if oz is not None:
            _check("chemistry.ozone_data.ozone_file",
                   getattr(oz, "ozone_file", None))
            for sector, spec in (getattr(oz, "by_sector", None) or {}).items():
                _check(f"chemistry.ozone_data.by_sector[{sector}]", spec.hourly_file)
        _check("chemistry.nox_file", getattr(chem, "nox_file", None))
        nox = getattr(chem, "nox_background", None)
        if nox is not None:
            _check("chemistry.nox_background.hourly_file", nox.hourly_file)
            for sector, spec in nox.by_sector.items():
                _check(f"chemistry.nox_background.by_sector[{sector}]", spec.hourly_file)
    if control.save_file is not None:
        _check("control.save_file.filename", control.save_file.filename)
        _check("control.save_file.alternate_filename",
               control.save_file.alternate_filename)
    if control.init_file is not None:
        _check("control.init_file.filename", control.init_file.filename)
    if control.multiyear is not None:
        _check("control.multiyear.save_file", control.multiyear.save_file)
        _check("control.multiyear.init_file", control.multiyear.init_file)

    out = project.output
    for attr in ("summary_file", "plot_file", "postfile"):
        _check(f"output.{attr}", getattr(out, attr, None))
    for mf in out.maxi_files:
        _check(f"output.maxi_files[{mf.source_group}/{mf.averaging_period}]", mf.filename)
    for period, group, fname in (out.plot_file_groups or []):
        _check(f"output.plot_file_groups[{group}/{period}]", fname)
    for label, entries in (("max_daily_files", out.max_daily_files),
                           ("max_daily_by_year_files", out.max_daily_by_year_files),
                           ("max_daily_contributions", out.max_daily_contributions)):
        for entry in entries:
            _check(f"output.{label}[{entry.source_group}]", entry.filename)


__all__ = [
    "PathTraversalError",
    "parse_aermod_input",
    "read_aermod_input",
]

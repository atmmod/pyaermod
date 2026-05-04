"""
AERMOD ``.inp`` file reader.

Parses a textual AERMOD control-file back into an :class:`AERMODProject`
so a round-trip is possible:

    >>> project = read_aermod_input("facility.inp")
    >>> project.write("facility_clone.inp")

Supported pathway keywords (v1.4):
    CO: TITLEONE, TITLETWO, MODELOPT (incl. OLM/PVMRM/ARM2/GRSM/NOCHKD),
        AVERTIME, POLLUTID, RUNORNOT, ELEVUNIT, FLAGPOLE, URBANOPT,
        LOW_WIND, HALFLIFE, DCAYCOEF, NO2STACK, NO2EQUIL, OZONEVAL,
        OZONEFIL, O3VALUES, ERRORFIL, DEBUGOPT
    SO: LOCATION (POINT/AREA/VOLUME/LINE/RLINE/OPENPIT/AREACIRC),
        SRCPARAM, SRCGROUP, BACKGRND, BGSECTOR, BACKUNIT,
        GASDEPOS, PARTDIAM, MASSFRAX, PARTDENS, URBANSRC,
        BUILDHGT, BUILDWID, BUILDLEN, XBADJ, YBADJ,
        EMISFACT, HOUREMIS, INCLUDED, ELEVUNIT
    RE: GRIDCART (XYINC), GRIDPOLR, DISCCART, EVALCART, DISCPOLR,
        ELEVUNIT, INCLUDED
    ME: SURFFILE, PROFFILE, SURFDATA, UAIRDATA, PROFBASE, STARTEND,
        WDROTATE, SITEDATA
    OU: RECTABLE, MAXTABLE

Unknown keywords are collected in :attr:`AERMODProject.unparsed_lines`
and preserved on write via the project's writer, but are not round-
tripped structurally. Opening a file this reader doesn't fully
understand therefore still succeeds; it just won't produce a
byte-identical output when rewritten.

The reader is permissive about whitespace but strict about pathway
order: each pathway must appear once, inside ``XX STARTING`` and
``XX FINISHED`` markers.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .input_generator import (
    AERMODProject,
    AreaCircSource,
    AreaSource,
    BackgroundConcentration,
    BackgroundSector,
    CartesianGrid,
    ChemistryMethod,
    ChemistryOptions,
    ControlPathway,
    DiscreteReceptor,
    GasDepositionParams,
    LineSource,
    MeteorologyPathway,
    OpenPitSource,
    OutputPathway,
    OzoneData,
    ParticleDepositionParams,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
    RLineSource,
    SourceGroupDefinition,
    SourcePathway,
    TerrainType,
    VolumeSource,
)

# ---------------------------------------------------------------------------
# Lexer / pathway splitter
# ---------------------------------------------------------------------------

PATHWAYS = ("CO", "SO", "RE", "ME", "OU", "EV")


@dataclass
class _PathwayBlock:
    name: str
    lines: List[Tuple[int, str]] = field(default_factory=list)


def _split_pathways(text: str) -> Dict[str, _PathwayBlock]:
    """Return a mapping of pathway name -> block.

    Raises ValueError on malformed input (missing STARTING/FINISHED,
    unknown pathway, etc.).
    """
    blocks: Dict[str, _PathwayBlock] = {}
    current: Optional[_PathwayBlock] = None

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

    Handles two AERMOD conventions inside a block:
    - Lines may start with the pathway code (e.g. ``SO BUILDHGT ...``);
      the prefix is stripped so the canonical keyword is the first
      output token.
    - Repeated values in shorthand form (``36*50.``) are expanded so
      downstream parsers see the full list.
    """
    out: List[Tuple[str, List[str], int]] = []
    pathway_upper = block.name.upper()
    for lineno, line in block.lines:
        toks = line.split()
        if not toks:
            continue
        # Strip leading pathway code if present (e.g. "SO BUILDHGT ..." -> "BUILDHGT ...")
        if toks[0].upper() == pathway_upper and len(toks) > 1:
            toks = toks[1:]
        toks = _expand_shorthand(toks)
        out.append((toks[0].upper(), toks[1:], lineno))
    return out


# ---------------------------------------------------------------------------
# Pathway parsers
# ---------------------------------------------------------------------------

_CHEM_METHODS: Dict[str, ChemistryMethod] = {
    "OLM": ChemistryMethod.OLM,
    "PVMRM": ChemistryMethod.PVMRM,
    "ARM2": ChemistryMethod.ARM2,
    "GRSM": ChemistryMethod.GRSM,
}


def _parse_control(block: _PathwayBlock) -> ControlPathway:
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

    # Chemistry options (populated by NO2STACK, OZONEVAL, OZONEFIL, MODELOPT method)
    chem_method: Optional[ChemistryMethod] = None
    no2_ratio: Optional[float] = None
    ozone_uniform: Optional[float] = None
    ozone_file: Optional[str] = None

    for kw, toks, _ln in _group_keywords(block):
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
                    terrain = TerrainType.FLAT
                elif up in ("ELEV", "ELEVATED"):
                    terrain = TerrainType.ELEVATED
                elif up == "FLATSRCS":
                    terrain = TerrainType.FLATSRCS
                elif up == "DFAULT":
                    reg_default = True
                elif up in _CHEM_METHODS:
                    chem_method = _CHEM_METHODS[up]
                elif up == "NOCHKD":
                    pass  # Recognized; no structural field
        elif kw == "AVERTIME":
            avertime = [t.upper() for t in toks]
        elif kw == "POLLUTID":
            pollutant = toks[0].upper() if toks else "OTHER"
        elif kw == "RUNORNOT":
            pass  # Presence implies RUN; NOT means skip, handled implicitly
        elif kw == "HALFLIFE":
            half_life = float(toks[0])
        elif kw == "DCAYCOEF":
            decay = float(toks[0])
        elif kw == "ELEVUNIT":
            elev_units = toks[0].upper() if toks else "METERS"
        elif kw == "FLAGPOLE":
            flagpole = float(toks[0]) if toks else None
        elif kw == "URBANOPT":
            urban = toks[0] if toks else None
            if len(toks) > 1:
                with contextlib.suppress(ValueError):
                    urban_pop = float(toks[1])
        elif kw == "LOW_WIND":
            low_wind = toks[0] if toks else None
        elif kw == "NO2STACK" and toks:
            with contextlib.suppress(ValueError):
                no2_ratio = float(toks[0])
        elif kw == "NO2EQUIL":
            pass  # Recognized; equilibrium NO2/NOx ratio has no structural field yet
        elif kw in ("OZONEVAL", "O3VALUES"):
            # Forms: "OZONEVAL <value> [units]",  "O3VALUES UNIFORM <value>",
            # "O3VALUES <filename>"
            if not toks:
                pass
            elif toks[0].upper() == "UNIFORM" and len(toks) >= 2:
                with contextlib.suppress(ValueError):
                    ozone_uniform = float(toks[1])
            else:
                # First token may be a numeric value (possibly followed by units)
                try:
                    ozone_uniform = float(toks[0])
                except ValueError:
                    # Non-numeric → treat as a file path
                    ozone_file = toks[0]
        elif kw == "OZONEFIL" and toks:
            ozone_file = toks[0]
        elif kw in ("ERRORFIL", "DEBUGOPT"):
            pass  # Recognized; no structural field

    # Build ChemistryOptions if any chemistry-related keywords were found
    chemistry: Optional[ChemistryOptions] = None
    if chem_method is not None or no2_ratio is not None \
            or ozone_uniform is not None or ozone_file is not None:
        ozone_data: Optional[OzoneData] = None
        if ozone_uniform is not None or ozone_file is not None:
            ozone_data = OzoneData(ozone_file=ozone_file, uniform_value=ozone_uniform)
        chemistry = ChemistryOptions(
            method=chem_method or ChemistryMethod.ARM2,
            ozone_data=ozone_data,
            default_no2_ratio=no2_ratio if no2_ratio is not None else 0.5,
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
        low_wind_option=low_wind,
        chemistry=chemistry,
    )


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


def _parse_sources(block: _PathwayBlock) -> SourcePathway:
    # LOCATION gives us each source's type and coordinates; SRCPARAM fills
    # in emission + physical parameters. Building-downwash keywords
    # (BUILDHGT, BUILDWID, ...) may appear on multiple lines per source
    # to cover 36 wind sectors; values accumulate in lists.
    locs: Dict[str, Dict[str, Any]] = {}
    src_types: Dict[str, str] = {}
    group_defs: List[SourceGroupDefinition] = []

    # Deposition data accumulated by source ID before source objects exist
    gas_dep_data: Dict[str, GasDepositionParams] = {}
    part_dep_data: Dict[str, Dict[str, List[float]]] = {}  # srcid -> {diameters/fractions/densities}
    urbansrc_data: Dict[str, str] = {}  # srcid -> urban_area_name

    # Background concentration accumulation
    bg_uniform: Optional[float] = None
    bg_period_values: Dict[str, float] = {}
    bg_sectors: List[BackgroundSector] = []
    bg_sector_values: Dict[Tuple[int, str], float] = {}

    for kw, toks, _ln in _group_keywords(block):
        if kw == "LOCATION":
            if len(toks) < 4:
                continue
            sid, stype = toks[0], toks[1].upper()
            x, y = float(toks[2]), float(toks[3])
            src_types[sid] = stype
            locs.setdefault(sid, {})
            locs[sid]["x_coord"] = x
            locs[sid]["y_coord"] = y
            # LINE / RLINE / RLINEXT LOCATION format is:
            #   srcid TYPE x_start y_start x_end y_end [elev]  (LINE/RLINE)
            #   srcid TYPE x_start y_start z_start x_end y_end z_end (RLINEXT)
            # Non-LINE sources use the 5th token as base_elevation.
            if stype in ("LINE", "RLINE") and len(toks) >= 6:
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
                continue
            sid = toks[0]
            params = [float(t) for t in toks[1:]]
            locs.setdefault(sid, {})["params"] = params
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
        elif kw == "SRCGROUP":
            if not toks:
                continue
            grp_name = toks[0]
            members = toks[1:]
            # Skip bare "SRCGROUP ALL" — it's auto-regenerated by the
            # writer from the sources list, and has no explicit members.
            if grp_name.upper() == "ALL" and not members:
                continue
            group_defs.append(SourceGroupDefinition(
                group_name=grp_name, member_source_ids=members,
            ))

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
                    pass  # File-based background; not stored structurally
        elif kw == "BGSECTOR":
            # BGSECTOR <dir1> <dir2> ...  — sector starting directions (degrees)
            for idx, tok in enumerate(toks, start=1):
                with contextlib.suppress(ValueError):
                    bg_sectors.append(BackgroundSector(
                        sector_id=idx, start_direction=float(tok)
                    ))
        elif kw == "BACKUNIT":
            pass  # Recognized (PPB/UG/M3); no structural field

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

        # ------------------------------------------------------------------
        # Urban source designation
        # ------------------------------------------------------------------
        elif kw == "URBANSRC":
            # URBANSRC srcid urban_area_name
            if len(toks) >= 2:
                urbansrc_data[toks[0]] = toks[1]

        # ------------------------------------------------------------------
        # Recognized but not structurally stored
        # ------------------------------------------------------------------
        elif kw in ("EMISFACT", "HOUREMIS", "INCLUDED", "ELEVUNIT"):
            pass  # Recognized keyword; no structural field in SourcePathway

    # Build source objects
    sources = []
    for sid, data in locs.items():
        stype = src_types.get(sid, "POINT")
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
        # AREAPOLY, BUOYLINE, RLINEXT: require additional multi-line
        # constructs (AREAVERT vertex lists, BLPINPUT parameter blocks,
        # per-endpoint z values) that we don't yet reconstruct. Skipped
        # with a soft-warning path so the rest of the project still parses.

        if src is None:
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

    return SourcePathway(sources=sources, group_definitions=group_defs, background=background)


def _parse_receptors(block: _PathwayBlock) -> ReceptorPathway:
    carts: Dict[str, Dict[str, Any]] = {}
    polars: Dict[str, Dict[str, Any]] = {}
    discretes: List[DiscreteReceptor] = []
    elev_units = "METERS"
    last_gridcart: Optional[str] = None

    for kw, toks, _ln in _group_keywords(block):
        if kw == "ELEVUNIT":
            elev_units = toks[0].upper() if toks else "METERS"

        elif kw == "GRIDCART":
            if len(toks) < 2:
                continue
            name = toks[0]
            action = toks[1].upper()
            carts.setdefault(name, {"grid_name": name})
            last_gridcart = name
            if action == "XYINC" and len(toks) >= 8:
                carts[name].update(
                    x_init=float(toks[2]), x_num=int(toks[3]), x_delta=float(toks[4]),
                    y_init=float(toks[5]), y_num=int(toks[6]), y_delta=float(toks[7]),
                )
            elif action in ("STA", "END"):
                pass  # just markers

        elif kw == "XYINC" and last_gridcart is not None and len(toks) >= 6:
            # AERMOD allows XYINC on a continuation line inside a GRIDCART block
            carts[last_gridcart].update(
                x_init=float(toks[0]), x_num=int(toks[1]), x_delta=float(toks[2]),
                y_init=float(toks[3]), y_num=int(toks[4]), y_delta=float(toks[5]),
            )

        elif kw == "GRIDPOLR":
            if len(toks) < 2:
                continue
            name = toks[0]
            action = toks[1].upper()
            polars.setdefault(name, {"grid_name": name})
            if action == "ORIG" and len(toks) >= 4:
                polars[name].update(
                    x_origin=float(toks[2]), y_origin=float(toks[3]),
                )
            elif action == "DIST" and len(toks) >= 4:
                # Two AERMOD forms:
                # (a) DIST init num delta  (3 args; num is integer)
                # (b) DIST d1 d2 d3 ...   (explicit list of distances)
                # Heuristic: if exactly 3 data args AND the 2nd looks
                # like an integer, assume form (a); else form (b).
                data_toks = toks[2:]
                if len(data_toks) == 3 and "." not in data_toks[1]:
                    with contextlib.suppress(ValueError):
                        polars[name].update(
                            dist_init=float(data_toks[0]),
                            dist_num=int(data_toks[1]),
                            dist_delta=float(data_toks[2]),
                        )
                else:
                    # Explicit distances: store num = len, init = first, delta = average spacing
                    distances = [float(d) for d in data_toks]
                    n = len(distances)
                    polars[name].update(
                        dist_init=distances[0],
                        dist_num=n,
                        dist_delta=(distances[-1] - distances[0]) / max(n - 1, 1),
                    )
            elif action == "GDIR" and len(toks) >= 4:
                # Two AERMOD forms:
                # (a1) GDIR init num delta — pyaermod writer (init first, float int float)
                # (a2) GDIR num init delta — EPA convention (int first)
                # (b)  GDIR d1 d2 d3 ...  — explicit direction list
                # Heuristic: if exactly 3 args, check which position is the integer.
                data_toks = toks[2:]
                if len(data_toks) == 3:
                    # Check position 1 (pyaermod convention: init num delta)
                    if "." not in data_toks[1]:
                        with contextlib.suppress(ValueError):
                            polars[name].update(
                                dir_init=float(data_toks[0]),
                                dir_num=int(data_toks[1]),
                                dir_delta=float(data_toks[2]),
                            )
                    # Else check position 0 (EPA convention: num init delta)
                    elif "." not in data_toks[0]:
                        with contextlib.suppress(ValueError):
                            polars[name].update(
                                dir_num=int(data_toks[0]),
                                dir_init=float(data_toks[1]),
                                dir_delta=float(data_toks[2]),
                            )
                    else:
                        dirs = [float(d) for d in data_toks]
                        polars[name].update(
                            dir_init=dirs[0], dir_num=3,
                            dir_delta=(dirs[-1] - dirs[0]) / 2,
                        )
                else:
                    # Explicit directions list
                    dirs = [float(d) for d in data_toks]
                    n = len(dirs)
                    polars[name].update(
                        dir_init=dirs[0],
                        dir_num=n,
                        dir_delta=(dirs[-1] - dirs[0]) / max(n - 1, 1) if n > 1 else 10.0,
                    )

        elif kw == "DISCCART":
            if len(toks) < 3:
                continue
            x, y, z = float(toks[0]), float(toks[1]), float(toks[2])
            z_hill = float(toks[3]) if len(toks) > 3 else 0.0
            z_flag = float(toks[4]) if len(toks) > 4 else 0.0
            discretes.append(DiscreteReceptor(
                x_coord=x, y_coord=y, z_elev=z,
                z_hill=z_hill, z_flag=z_flag,
            ))

        elif kw in ("EVALCART", "DISCPOLR", "INCLUDED"):
            pass  # Recognized; no structural field in ReceptorPathway

    return ReceptorPathway(
        cartesian_grids=[CartesianGrid(**d) for d in carts.values()],
        polar_grids=[PolarGrid(**d) for d in polars.values()],
        discrete_receptors=discretes,
        elevation_units=elev_units,
    )


def _parse_meteorology(block: _PathwayBlock) -> MeteorologyPathway:
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

    for kw, toks, _ln in _group_keywords(block):
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
        elif kw == "STARTEND" and len(toks) >= 6:
            dates.update(
                start_year=int(toks[0]),
                start_month=int(toks[1]),
                start_day=int(toks[2]),
                end_year=int(toks[3]),
                end_month=int(toks[4]),
                end_day=int(toks[5]),
            )
        elif kw == "WDROTATE" and toks:
            wind_rotation = float(toks[0])
        elif kw == "SITEDATA":
            pass  # Recognized; site-specific met data; no structural field

    return MeteorologyPathway(
        **kw_map, **dates,
        wind_rotation=wind_rotation,
    )


def _parse_output(block: _PathwayBlock) -> OutputPathway:
    receptor_table = False
    max_table = False
    day_table = False
    rect_rank = 10
    max_rank = 10
    summary_file: Optional[str] = None
    max_file: Optional[str] = None
    plot_file: Optional[str] = None
    plot_file_averaging = "ANNUAL"
    plot_file_groups: List[Tuple[str, str, str]] = []
    postfile: Optional[str] = None
    postfile_averaging: Optional[str] = None
    postfile_source_group = "ALL"
    postfile_format = "PLOT"

    for kw, toks, _ln in _group_keywords(block):
        if kw == "RECTABLE" and len(toks) >= 2:
            receptor_table = True
            # AERMOD accepts either a numeric rank or the special keyword
            # form "FIRST-THIRD" (still represented as rank 3).
            rank_tok = toks[1]
            with contextlib.suppress(ValueError):
                rect_rank = int(rank_tok)
        elif kw == "MAXTABLE" and len(toks) >= 2:
            max_table = True
            with contextlib.suppress(ValueError):
                max_rank = int(toks[1])
        elif kw == "DAYTABLE":
            day_table = True
        elif kw == "SUMMFILE" and toks:
            summary_file = toks[0]
        elif kw == "MAXIFILE" and toks:
            max_file = toks[0]
        elif kw == "PLOTFILE":
            # PLOTFILE <avg_period> <source_group> <rank> <filename>
            if len(toks) >= 4:
                period, group, _rank, fname = toks[0], toks[1], toks[2], toks[3]
                if group.upper() == "ALL" and plot_file is None:
                    plot_file = fname
                    plot_file_averaging = period
                else:
                    plot_file_groups.append((period, group, fname))
        elif kw == "POSTFILE":
            # POSTFILE <avg_period> <source_group> <format> <filename>
            if len(toks) >= 4:
                postfile_averaging = toks[0]
                postfile_source_group = toks[1]
                postfile_format = toks[2].upper()
                postfile = toks[3]

    return OutputPathway(
        receptor_table=receptor_table,
        receptor_table_rank=rect_rank,
        max_table=max_table,
        max_table_rank=max_rank,
        day_table=day_table,
        summary_file=summary_file,
        max_file=max_file,
        plot_file=plot_file,
        plot_file_averaging=plot_file_averaging,
        plot_file_groups=plot_file_groups,
        postfile=postfile,
        postfile_averaging=postfile_averaging,
        postfile_source_group=postfile_source_group,
        postfile_format=postfile_format,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_aermod_input(text: str) -> AERMODProject:
    """Parse the text of an AERMOD ``.inp`` file into an AERMODProject."""
    blocks = _split_pathways(text)

    for required in ("CO", "SO", "RE", "ME"):
        if required not in blocks:
            raise ValueError(f"AERMOD input is missing required pathway {required}")

    control = _parse_control(blocks["CO"])
    sources = _parse_sources(blocks["SO"])
    receptors = _parse_receptors(blocks["RE"])
    meteorology = _parse_meteorology(blocks["ME"])
    output = _parse_output(blocks.get("OU", _PathwayBlock("OU")))

    return AERMODProject(
        control=control,
        sources=sources,
        receptors=receptors,
        meteorology=meteorology,
        output=output,
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
    - output.summary_file / max_file / plot_file / postfile
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

    chem = getattr(project.control, "chemistry", None)
    if chem is not None:
        oz = getattr(chem, "ozone_data", None)
        if oz is not None:
            _check("chemistry.ozone_data.ozone_file",
                   getattr(oz, "ozone_file", None))
        _check("chemistry.nox_file", getattr(chem, "nox_file", None))

    out = project.output
    for attr in ("summary_file", "max_file", "plot_file", "postfile"):
        _check(f"output.{attr}", getattr(out, attr, None))
    for period, group, fname in (out.plot_file_groups or []):
        _check(f"output.plot_file_groups[{group}/{period}]", fname)


__all__ = [
    "parse_aermod_input",
    "read_aermod_input",
    "PathTraversalError",
]

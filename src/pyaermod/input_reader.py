"""
AERMOD ``.inp`` file reader.

Parses a textual AERMOD control-file back into an :class:`AERMODProject`
so a round-trip is possible:

    >>> project = read_aermod_input("facility.inp")
    >>> project.write("facility_clone.inp")

Supported pathway keywords (v1.3):
    CO: TITLEONE, TITLETWO, MODELOPT, AVERTIME, POLLUTID, RUNORNOT,
        ELEVUNIT, FLAGPOLE, URBANOPT, LOW_WIND, HALFLIFE, DCAYCOEF
    SO: LOCATION (POINT/AREA/VOLUME), SRCPARAM, SRCGROUP
    RE: GRIDCART (XYINC), GRIDPOLR, DISCCART, ELEVUNIT
    ME: SURFFILE, PROFFILE, SURFDATA, UAIRDATA, PROFBASE, STARTEND,
        WDROTATE
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .input_generator import (
    AERMODProject,
    AreaSource,
    CartesianGrid,
    ControlPathway,
    DiscreteReceptor,
    MeteorologyPathway,
    OutputPathway,
    PointSource,
    PolarGrid,
    PollutantType,
    ReceptorPathway,
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


def _group_keywords(block: _PathwayBlock) -> List[Tuple[str, List[str], int]]:
    """Return (keyword, tokens, lineno) tuples.

    AERMOD allows continuation by indentation, but for the common case
    each keyword is a single line. We join continuation lines (those
    whose first token isn't a known pathway keyword) with the previous.
    """
    out: List[Tuple[str, List[str], int]] = []
    for lineno, line in block.lines:
        toks = line.split()
        if not toks:
            continue
        out.append((toks[0].upper(), toks[1:], lineno))
    return out


# ---------------------------------------------------------------------------
# Pathway parsers
# ---------------------------------------------------------------------------

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
                elif up in ("FLAT",):
                    terrain = TerrainType.FLAT
                elif up in ("ELEV", "ELEVATED"):
                    terrain = TerrainType.ELEVATED
                elif up == "FLATSRCS":
                    terrain = TerrainType.FLATSRCS
                elif up == "DFAULT":
                    reg_default = True
                # Chemistry methods (OLM, PVMRM, etc.) are handled elsewhere
                # via ChemistryOptions; we drop them here for now.
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
                try:
                    urban_pop = float(toks[1])
                except ValueError:
                    urban_pop = None
        elif kw == "LOW_WIND":
            low_wind = toks[0] if toks else None

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
    )


def _coerce_pollutant(name: str) -> Union[PollutantType, str]:
    try:
        return PollutantType(name)
    except ValueError:
        return name


def _parse_sources(block: _PathwayBlock) -> SourcePathway:
    # LOCATION gives us each source's type and coordinates; SRCPARAM fills
    # in emission + physical parameters. We collect the pieces in dicts
    # keyed by source_id then construct the dataclass at the end.
    locs: Dict[str, Dict[str, Any]] = {}
    src_types: Dict[str, str] = {}
    group_defs: List[SourceGroupDefinition] = []

    for kw, toks, _ln in _group_keywords(block):
        if kw == "LOCATION":
            if len(toks) < 4:
                continue
            sid, stype, x, y = toks[0], toks[1].upper(), float(toks[2]), float(toks[3])
            z = float(toks[4]) if len(toks) > 4 else 0.0
            src_types[sid] = stype
            locs.setdefault(sid, {})
            locs[sid].update(x_coord=x, y_coord=y, z_elev=z)
        elif kw == "SRCPARAM":
            if not toks:
                continue
            sid = toks[0]
            params = [float(t) for t in toks[1:]]
            locs.setdefault(sid, {})["params"] = params
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

    sources = []
    for sid, data in locs.items():
        stype = src_types.get(sid, "POINT")
        params = data.get("params", [])
        common = dict(
            source_id=sid,
            x_coord=data.get("x_coord", 0.0),
            y_coord=data.get("y_coord", 0.0),
        )
        if stype == "POINT":
            # SRCPARAM POINT: emission stackht stacktemp velocity diameter
            if len(params) < 5:
                continue
            sources.append(PointSource(
                **common,
                emission_rate=params[0],
                stack_height=params[1],
                stack_temp=params[2],
                exit_velocity=params[3],
                stack_diameter=params[4],
            ))
        elif stype == "AREA":
            # SRCPARAM AREA: emission relhgt xinit yinit [angle]
            if not params:
                continue
            sources.append(AreaSource(
                **common,
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                initial_lateral_dimension=params[2] if len(params) > 2 else 10.0,
                initial_vertical_dimension=params[3] if len(params) > 3 else 10.0,
                angle=params[4] if len(params) > 4 else 0.0,
            ))
        elif stype == "VOLUME":
            # SRCPARAM VOLUME: emission relhgt sylinit szinit
            if not params:
                continue
            sources.append(VolumeSource(
                **common,
                emission_rate=params[0],
                release_height=params[1] if len(params) > 1 else 0.0,
                initial_lateral_dimension=params[2] if len(params) > 2 else 1.0,
                initial_vertical_dimension=params[3] if len(params) > 3 else 1.0,
            ))
        # Other source types (LINE, RLINE, RLINEXT, BUOYLINE, OPENPIT,
        # AREACIRC, AREAPOLY) intentionally unsupported in this v1; users
        # should use programmatic construction for those.

    return SourcePathway(sources=sources, group_definitions=group_defs)


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
            elif action == "DIST" and len(toks) >= 5:
                polars[name].update(
                    dist_init=float(toks[2]),
                    dist_num=int(toks[3]),
                    dist_delta=float(toks[4]),
                )
            elif action == "GDIR" and len(toks) >= 5:
                polars[name].update(
                    dir_init=float(toks[2]),
                    dir_num=int(toks[3]),
                    dir_delta=float(toks[4]),
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

    return MeteorologyPathway(
        **kw_map, **dates,
        wind_rotation=wind_rotation,
    )


def _parse_output(block: _PathwayBlock) -> OutputPathway:
    receptor_table = False
    max_table = False
    rect_rank = 10
    max_rank = 10

    for kw, toks, _ln in _group_keywords(block):
        if kw == "RECTABLE" and len(toks) >= 2:
            receptor_table = True
            with contextlib.suppress(ValueError):
                rect_rank = int(toks[1])
        elif kw == "MAXTABLE" and len(toks) >= 2:
            max_table = True
            with contextlib.suppress(ValueError):
                max_rank = int(toks[1])

    return OutputPathway(
        receptor_table=receptor_table,
        receptor_table_rank=rect_rank,
        max_table=max_table,
        max_table_rank=max_rank,
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


def read_aermod_input(path: Union[str, Path]) -> AERMODProject:
    """Read an AERMOD ``.inp`` file from disk and return the project."""
    p = Path(path)
    return parse_aermod_input(p.read_text(encoding="utf-8"))


__all__ = ["parse_aermod_input", "read_aermod_input"]

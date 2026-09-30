"""
PyAERMOD AERMAP Input Generator

Generates AERMAP input files for terrain preprocessing.
AERMAP is the EPA's terrain preprocessor for AERMOD.

AERMAP reads Digital Elevation Model (DEM) data and calculates:
- Receptor elevations
- Hill heights (for terrain-following calculations)
- Source elevations
"""

from dataclasses import dataclass, field, replace
from typing import List, Optional, Tuple, Union

from .receptors import CartesianGrid, PolarGrid


@dataclass
class AERMAPDomain:
    """Domain definition for AERMAP processing"""
    # Anchor point (SW corner)
    anchor_x: float  # UTM Easting
    anchor_y: float  # UTM Northing

    # Domain size
    num_x_points: int
    num_y_points: int
    spacing: float  # meters

    # DEM files
    dem_files: List[str] = field(default_factory=list)

    # UTM zone and datum
    utm_zone: int = 16
    datum: str = "NAD83"  # or "NAD27", "WGS84"


@dataclass
class AERMAPReceptor:
    """Receptor definition for AERMAP"""
    receptor_id: str
    x_coord: float
    y_coord: float
    elevation: Optional[float] = None  # If None, AERMAP will calculate from DEM


@dataclass
class AERMAPSource:
    """Source definition for AERMAP.

    ``source_type`` is the AERMAP source type (``AERMAP_SOURCE_TYPES``).
    A ``LINE``, ``RLINE`` or ``BUOYLINE`` source also needs its end point
    (``x_end``, ``y_end``), and a ``LINE`` its ``width``: AERMAP takes the
    elevation of RLINE and BUOYLINE sources at the midpoint of the two
    ends, and of a LINE source at the south-west corner of its equivalent
    area (SOLOCA in aermap.f). Every other type is placed at
    (``x_coord``, ``y_coord``).
    """
    source_id: str
    x_coord: float
    y_coord: float
    elevation: Optional[float] = None  # If None, AERMAP will calculate from DEM
    source_type: str = "POINT"
    x_end: Optional[float] = None
    y_end: Optional[float] = None
    width: Optional[float] = None  # LINE only: the width in SRCPARAM, metres


# AERMAP's datum codes for the NADA field of ANCHORXY, from the NADN table
# in mod_main1.f of AERMAP 24142 (0 means "apply no datum shift").
AERMAP_DATUM_CODES = {
    "NAD27": 1,
    "WGS72": 2,
    "WGS84": 3,
    "NAD83": 4,
}

# TERRHGTS takes EXTRACT or PROVIDED (TERRHT in aermap.f). "ELEVATED" is
# what this module used to write; AERMAP rejects it (E203), and it is read
# here as the EXTRACT it was meant to be.
_TERRHGTS_OPTIONS = {"EXTRACT": "EXTRACT", "PROVIDED": "PROVIDED", "ELEVATED": "EXTRACT"}

# AERMAP stores each runstream field in CHARACTER*200 (ILEN_FLD in mod_main1.f).
_MAX_FIELD_LENGTH = 200


def _quote_field(value: str, what: str) -> str:
    """Return ``value`` as one AERMAP runstream field.

    AERMAP splits a line on blanks unless the field is in double quotes
    (DEFINE in aermap.f), so a path with a space is quoted.
    """
    if len(value) > _MAX_FIELD_LENGTH:
        raise ValueError(
            f"{what} is {len(value)} characters long; AERMAP reads at most "
            f"{_MAX_FIELD_LENGTH} (move the file or use a relative path): {value}"
        )
    if '"' in value:
        raise ValueError(f"{what} contains a double quote, which AERMAP cannot read: {value}")
    return f'"{value}"' if any(c.isspace() for c in value) else value


def _infer_dem_format(dem_files: List[str]) -> str:
    """``DEM`` when every file is a USGS ``.dem`` file, otherwise ``NED`` (GeoTIFF)."""
    if dem_files and all(str(f).lower().endswith(".dem") for f in dem_files):
        return "DEM"
    return "NED"


# The source types SOLOCA in aermap.f (AERMAP 24142) accepts; any other is
# E203. The first group is placed at one point (LOCATION id type x y
# [zelev]); RLINE and BUOYLINE take both ends (x1 y1 x2 y2 [zelev]) and
# LINE both ends and its width (x1 y1 x2 y2 width [zelev]).
_AERMAP_POINT_TYPES = ("POINT", "POINTCAP", "POINTHOR", "VOLUME", "AREA", "AREAPOLY", "AREACIRC", "OPENPIT")
_AERMAP_LINE_TYPES = ("LINE", "RLINE", "BUOYLINE")
AERMAP_SOURCE_TYPES = _AERMAP_POINT_TYPES + _AERMAP_LINE_TYPES

# AERMAP reads source IDs of up to 12 characters (SOLOCA, E206) and
# receptor network IDs of up to 8: a longer network ID is cut to 8 in the
# receptor file, so its elevations could not be matched back to it.
_MAX_SOURCE_ID = 12
_MAX_NETWORK_ID = 8


def _aermap_sources_for(src) -> Tuple[List["AERMAPSource"], List[Tuple[float, float]]]:
    """The AERMAP sources that stand for one AERMOD source, and its extent points.

    Each AERMOD source is written as the AERMAP type that gets its
    elevation where AERMOD expects it: the AERMOD type itself where AERMAP
    has it, SWPOINT as POINT and RLINEXT as RLINE (AERMAP 24142 has
    neither), an AREAPOLY at its first vertex (the LOCATION AERMOD
    requires), and each BUOYLINE segment under its own ID. Raises
    ``ValueError`` for a source it cannot place, rather than leaving the
    source without an elevation.
    """
    from pyaermod.sources import (
        AreaCircSource,
        AreaPolySource,
        AreaSource,
        BuoyLineSource,
        LineSource,
        OpenPitSource,
        PointSource,
        RLineExtSource,
        RLineSource,
        SidewashPointSource,
        VolumeSource,
    )

    point_types = {
        AreaSource: "AREA",
        AreaCircSource: "AREACIRC",
        VolumeSource: "VOLUME",
        OpenPitSource: "OPENPIT",
        SidewashPointSource: "POINT",
    }
    if isinstance(src, PointSource):  # POINT, POINTCAP, POINTHOR
        out = [AERMAPSource(src.source_id, src.x_coord, src.y_coord, source_type=src.location_type)]
    elif type(src) in point_types:
        out = [AERMAPSource(src.source_id, src.x_coord, src.y_coord, source_type=point_types[type(src)])]
    elif isinstance(src, AreaPolySource):
        if not src.vertices:
            raise ValueError(f"AREAPOLY source {src.source_id} has no vertices to place for AERMAP")
        x0, y0 = src.vertices[0]
        return (
            [AERMAPSource(src.source_id, x0, y0, source_type="AREAPOLY")],
            [(float(x), float(y)) for x, y in src.vertices],
        )
    elif isinstance(src, LineSource):
        out = [AERMAPSource(
            src.source_id, src.x_start, src.y_start, source_type="LINE",
            x_end=src.x_end, y_end=src.y_end, width=src.initial_lateral_dimension,
        )]
    elif isinstance(src, (RLineSource, RLineExtSource)):
        out = [AERMAPSource(
            src.source_id, src.x_start, src.y_start, source_type="RLINE",
            x_end=src.x_end, y_end=src.y_end,
        )]
    elif isinstance(src, BuoyLineSource):
        if not src.line_segments:
            raise ValueError(f"BUOYLINE source {src.source_id} has no line segments to place for AERMAP")
        out = [
            AERMAPSource(
                seg.source_id, seg.x_start, seg.y_start, source_type="BUOYLINE",
                x_end=seg.x_end, y_end=seg.y_end,
            )
            for seg in src.line_segments
        ]
    else:
        raise ValueError(
            f"AERMAP input cannot place source {getattr(src, 'source_id', src)!r} "
            f"of type {type(src).__name__}"
        )
    points = []
    for s in out:
        points.append((s.x_coord, s.y_coord))
        if s.x_end is not None and s.y_end is not None:
            points.append((s.x_end, s.y_end))
    return out, points


def _value_lines(head: str, values: List[float], per_line: int = 6) -> List[str]:
    """``head v1 v2 ...`` lines; AERMAP adds up the values over the lines."""
    return [
        head + "  " + " ".join(f"{v:.2f}" for v in values[start:start + per_line])
        for start in range(0, len(values), per_line)
    ]


@dataclass
class AERMAPProject:
    """
    AERMAP project configuration

    Generates terrain elevations for receptors and sources.

    ``to_aermap_input`` writes the runstream syntax of EPA's AERMAP 24142,
    the current release: the pathways in the order CO, SO, RE, OU, the
    mandatory ``ANCHORXY`` and ``RUNORNOT`` keywords, ``TERRHGTS EXTRACT``
    or ``PROVIDED``, and the ``RECEPTOR`` and ``SOURCLOC`` output files.

    Receptor networks. ``grids`` holds AERMOD ``CartesianGrid`` and
    ``PolarGrid`` objects, each written as a ``GRIDCART`` or ``GRIDPOLR``
    block under its ``grid_name`` (at most 8 characters, unique). The
    older single-grid fields (``grid_receptor``, ``grid_x_init`` ...)
    still work and write a network named ``GRID``. A polar grid centred
    on a source (``origin_source_id``) is written with that source's
    coordinates, which must be one of ``sources`` of a single-point type.

    NADCON. When the DEM files' datum differs from ``datum``, AERMAP
    shifts between the two with the NADCON grid files (``conus.las``,
    ``conus.los`` ...) and stops with E365 if it cannot find them.
    ``nad_grids_dir`` names the directory that holds them (``NADGRIDS``);
    without it AERMAP looks in the working directory.

    Coordinates. Receptor and source coordinates are in the "user"
    system of the AERMOD deck. ``ANCHORXY`` ties one user point
    (``anchor_x``, ``anchor_y``) to a UTM point (``anchor_utm_x``,
    ``anchor_utm_y``, which default to the same values, i.e. user
    coordinates are UTM coordinates in ``utm_zone``). ``datum`` is the
    datum of those coordinates and becomes AERMAP's NADA code
    (``AERMAP_DATUM_CODES``, or an integer 0 to 7 given directly).

    Domain. ``DOMAINXY`` is written when all four of ``domain_x_min``,
    ``domain_y_min``, ``domain_x_max`` and ``domain_y_max`` are set (UTM
    metres, zone ``utm_zone``). AERMAP searches only this area for the
    hill heights, so it must take in every terrain feature that rises
    above a 10% slope from any receptor (the rule in sub_calchc.f), or the
    hill heights come out too low without any warning. The whole area
    must also lie inside the DEM files (otherwise AERMAP stops with
    E310). Without it AERMAP searches the full extent of the DEM files,
    which is the safe default.

    Terrain heights. ``terrain_type`` is ``"EXTRACT"`` (AERMAP takes the
    elevations from the DEM; any ``elevation`` on a receptor or source is
    left out of the deck, since AERMAP would ignore it) or ``"PROVIDED"``
    (every receptor and source must carry its ``elevation``; AERMAP then
    computes only the receptors' hill heights and writes no source file,
    so ``SOURCLOC`` is left out). ``"ELEVATED"`` is read as ``"EXTRACT"``.

    AERMAP has no receptor IDs: ``AERMAPReceptor.receptor_id`` is kept
    for the caller's bookkeeping and is not written. AERMAP writes its
    messages to ``<input stem>.out`` beside the input file, not to a file
    the deck names, so ``message_file`` is not written either.
    """

    # Job control
    job_id: str = "AERMAP"
    title_one: str = "AERMAP Terrain Processing"
    title_two: Optional[str] = None

    # Terrain data
    dem_files: List[str] = field(default_factory=list)
    dem_format: str = "NED"  # "NED" (GeoTIFF) or "DEM" (USGS native format)

    # Anchor point: user coordinates of the point tied to UTM (ANCHORXY)
    anchor_x: Optional[float] = None
    anchor_y: Optional[float] = None
    utm_zone: int = 16
    datum: Union[str, int] = "NAD83"

    # Terrain heights: "EXTRACT" or "PROVIDED" (see the class docstring)
    terrain_type: str = "EXTRACT"

    # Receptors and sources
    receptors: List[AERMAPReceptor] = field(default_factory=list)
    sources: List[AERMAPSource] = field(default_factory=list)

    # Grid receptors (alternative to discrete receptors)
    grid_receptor: bool = False
    grid_x_init: float = 0.0
    grid_y_init: float = 0.0
    grid_x_num: int = 10
    grid_y_num: int = 10
    grid_spacing: float = 100.0

    # Output files
    receptor_output: str = "aermap_receptors.out"
    source_output: str = "aermap_sources.out"
    message_file: str = "aermap.msg"  # not written: see the class docstring

    # UTM coordinates of the anchor point; default to anchor_x / anchor_y
    anchor_utm_x: Optional[float] = None
    anchor_utm_y: Optional[float] = None

    # Domain for the hill-height search, UTM metres (DOMAINXY); optional
    domain_x_min: Optional[float] = None
    domain_y_min: Optional[float] = None
    domain_x_max: Optional[float] = None
    domain_y_max: Optional[float] = None

    # Grid spacing in y; defaults to grid_spacing
    grid_y_spacing: Optional[float] = None

    # Receptor networks: AERMOD CartesianGrid / PolarGrid objects, each
    # written under its own grid_name (see the class docstring)
    grids: List[Union[CartesianGrid, PolarGrid]] = field(default_factory=list)

    # Directory holding the NADCON grid files (NADGRIDS); optional
    nad_grids_dir: Optional[str] = None

    @classmethod
    def from_aermod_project(
        cls,
        aermod_project,
        dem_files: List[str],
        utm_zone: int = 16,
        datum: str = "NAD83",
        buffer: Optional[float] = None,
        dem_format: Optional[str] = None,
        nad_grids_dir: Optional[str] = None,
    ) -> "AERMAPProject":
        """Create an AERMAPProject from an AERMODProject.

        Every source, every Cartesian and polar grid and every discrete
        receptor of the AERMOD project is written, so AERMAP gives each of
        them an elevation. Each source is written as the AERMAP type that
        places its elevation where AERMOD expects it (the AERMOD type
        itself where AERMAP 24142 has it; SWPOINT as POINT, RLINEXT as
        RLINE, an AREAPOLY at its first vertex and each BUOYLINE segment
        under its own ID). A source type AERMAP cannot place raises
        ``ValueError`` rather than being left without an elevation.

        The AERMOD coordinates are taken as UTM coordinates in
        ``utm_zone``. By default no ``DOMAINXY`` is written, so AERMAP
        searches the whole DEM for hill heights. With ``buffer`` the
        domain is the project's extent widened by ``buffer`` metres on
        every side: AERMAP then ignores terrain outside it, so the buffer
        must take in every feature that rises above a 10% slope from any
        receptor, and the DEM files must cover the whole domain.

        Parameters
        ----------
        aermod_project : AERMODProject
        dem_files : list of str
            DEM file paths.
        utm_zone : int
        datum : str
            Datum of the AERMOD coordinates. When it differs from the DEM
            files' datum (USGS ``.dem`` files are usually NAD27), AERMAP
            needs the NADCON grid files: see ``nad_grids_dir``.
        buffer : float, optional
            Metres around the project's extent for ``DOMAINXY``; ``None``
            (the default) writes no domain.
        dem_format : str, optional
            ``"NED"`` (GeoTIFF) or ``"DEM"`` (USGS native format). By
            default ``"DEM"`` when every file ends in ``.dem``, otherwise
            ``"NED"``.
        nad_grids_dir : str, optional
            Directory of the NADCON grid files (``NADGRIDS``).

        Returns
        -------
        AERMAPProject
        """
        sources: List[AERMAPSource] = []
        points: List[Tuple[float, float]] = []
        for src in aermod_project.sources.sources:
            placed, extent = _aermap_sources_for(src)
            sources.extend(placed)
            points.extend(extent)
        where = {s.source_id: (s.x_coord, s.y_coord) for s in sources}

        receptors = aermod_project.receptors
        grids: List[Union[CartesianGrid, PolarGrid]] = []
        for cgrid in receptors.cartesian_grids:
            grids.append(replace(cgrid, grid_elevations=None, grid_hills=None, grid_flags=None))
            xs, ys = cgrid.x_values(), cgrid.y_values()
            if xs and ys:
                points += [(min(xs), min(ys)), (max(xs), max(ys))]
        for pgrid in receptors.polar_grids:
            grids.append(replace(pgrid, elevations=None, hills=None, flags=None))
            # An unknown origin source is reported by to_aermap_input.
            x0, y0 = where.get(pgrid.origin_source_id or "", (pgrid.x_origin, pgrid.y_origin))
            reach = max((abs(d) for d in pgrid.ring_distances()), default=0.0)
            points += [(x0 - reach, y0 - reach), (x0 + reach, y0 + reach)]
        for rec in receptors.discrete_receptors:
            points.append((rec.x_coord, rec.y_coord))

        if not points:
            raise ValueError("No source or receptor coordinates found in project")

        all_x = [p[0] for p in points]
        all_y = [p[1] for p in points]
        aermap = cls(
            title_one=f"AERMAP for {aermod_project.control.title_one}",
            dem_files=dem_files,
            dem_format=dem_format or _infer_dem_format(dem_files),
            # AERMOD coordinates are UTM: anchor a point to itself.
            anchor_x=min(all_x),
            anchor_y=min(all_y),
            utm_zone=utm_zone,
            datum=datum,
            terrain_type="EXTRACT",
            sources=sources,
            grids=grids,
            nad_grids_dir=nad_grids_dir,
        )
        if buffer is not None:
            aermap.domain_x_min = min(all_x) - buffer
            aermap.domain_y_min = min(all_y) - buffer
            aermap.domain_x_max = max(all_x) + buffer
            aermap.domain_y_max = max(all_y) + buffer

        for i, rec in enumerate(receptors.discrete_receptors):
            aermap.add_receptor(AERMAPReceptor(f"R{i + 1:04d}", rec.x_coord, rec.y_coord))

        return aermap

    def add_receptor(self, receptor: AERMAPReceptor):
        """Add a discrete receptor"""
        self.receptors.append(receptor)

    def add_source(self, source: AERMAPSource):
        """Add a source"""
        self.sources.append(source)

    def _terrhgts(self) -> str:
        option = _TERRHGTS_OPTIONS.get(str(self.terrain_type).upper())
        if option is None:
            raise ValueError(
                f"terrain_type={self.terrain_type!r}: AERMAP's TERRHGTS takes "
                "'EXTRACT' (elevations from the DEM) or 'PROVIDED' (elevations "
                "given on each receptor and source). Flat terrain needs no AERMAP "
                "run: use TerrainType.FLAT in the AERMOD deck instead."
            )
        return option

    def _datum_code(self) -> int:
        if isinstance(self.datum, int) and not isinstance(self.datum, bool):
            code = self.datum
        else:
            code = AERMAP_DATUM_CODES.get(str(self.datum).upper(), -1)
        if not 0 <= code <= 7:
            raise ValueError(
                f"datum={self.datum!r}: use one of {sorted(AERMAP_DATUM_CODES)} "
                "or an AERMAP NADA code from 0 to 7"
            )
        return code

    def _datatype(self) -> str:
        fmt = str(self.dem_format).upper()
        # DATTYP in aermap.f checks only the first three characters of DEM
        # (older decks say DEM1 or DEM7).
        if fmt != "NED" and not fmt.startswith("DEM"):
            raise ValueError(
                f"dem_format={self.dem_format!r}: AERMAP reads 'NED' (GeoTIFF) "
                "or 'DEM' (USGS native format) files"
            )
        return fmt

    def _domain_card(self) -> Optional[str]:
        corners = (self.domain_x_min, self.domain_y_min, self.domain_x_max, self.domain_y_max)
        if all(c is None for c in corners):
            return None
        if any(c is None for c in corners):
            raise ValueError(
                "set all four of domain_x_min, domain_y_min, domain_x_max and "
                "domain_y_max, or none of them"
            )
        x_min, y_min, x_max, y_max = (float(c) for c in corners if c is not None)
        if x_min >= x_max or y_min >= y_max:
            raise ValueError(
                f"domain min ({x_min}, {y_min}) must be south-west of max ({x_max}, {y_max})"
            )
        zone = self.utm_zone
        return f"   DOMAINXY  {x_min:.2f} {y_min:.2f} {zone} {x_max:.2f} {y_max:.2f} {zone}"

    def _nadgrids_card(self) -> Optional[str]:
        if not self.nad_grids_dir:
            return None
        path = str(self.nad_grids_dir)
        # DGRIDS in sub_nadcon.f opens NGPATH//'conus.las' with nothing in
        # between, so the directory needs its trailing separator.
        if not path.endswith(("/", "\\")):
            path += "/"
        return f"   NADGRIDS  {_quote_field(path, 'nad_grids_dir')}"

    @staticmethod
    def _location_card(src: AERMAPSource, provided: bool) -> str:
        """The SO LOCATION card for one source, in SOLOCA's field layout."""
        stype = str(src.source_type).upper()
        if stype not in AERMAP_SOURCE_TYPES:
            raise ValueError(
                f"source {src.source_id}: AERMAP 24142 has no source type {src.source_type!r} "
                f"(E203); use one of {', '.join(AERMAP_SOURCE_TYPES)}"
            )
        if len(src.source_id) > _MAX_SOURCE_ID or not src.source_id or " " in src.source_id:
            raise ValueError(
                f"source ID {src.source_id!r}: AERMAP reads IDs of 1 to {_MAX_SOURCE_ID} "
                "characters with no blanks (E206)"
            )
        fields = f"{src.x_coord:12.2f} {src.y_coord:12.2f}"
        if stype in _AERMAP_LINE_TYPES:
            if src.x_end is None or src.y_end is None:
                raise ValueError(f"{stype} source {src.source_id} needs x_end and y_end")
            fields += f" {src.x_end:12.2f} {src.y_end:12.2f}"
            if stype == "LINE":
                if src.width is None or src.width <= 0:
                    raise ValueError(
                        f"LINE source {src.source_id} needs its width (> 0 m): AERMAP "
                        "places it at the south-west corner of its equivalent area (E201 without it)"
                    )
                fields += f" {src.width:8.2f}"
        if provided:
            fields += f" {src.elevation:10.2f}"
        return f"   LOCATION  {src.source_id:<12} {stype:<7} {fields}"

    def _network_names(self) -> List[str]:
        names = ["GRID"] if self.grid_receptor else []
        names += [g.grid_name for g in self.grids]
        for name in names:
            if not name or len(name) > _MAX_NETWORK_ID or " " in name:
                raise ValueError(
                    f"grid name {name!r}: AERMAP reads network IDs of 1 to "
                    f"{_MAX_NETWORK_ID} characters with no blanks"
                )
        repeated = sorted({n for n in names if names.count(n) > 1})
        if repeated:
            raise ValueError(
                f"grid names must be unique (the legacy grid is named GRID): {', '.join(repeated)}"
            )
        return names

    def _grid_lines(self, grid: Union[CartesianGrid, PolarGrid]) -> List[str]:
        """A GRIDCART or GRIDPOLR block in AERMAP's syntax (RECART / REPOLR in aermap.f)."""
        name = f"{grid.grid_name:<8}"
        if isinstance(grid, CartesianGrid):
            head = f"   GRIDCART  {name}"
            xs, ys = grid.x_values(), grid.y_values()
            if not xs or not ys:
                raise ValueError(f"Cartesian grid {grid.grid_name} has no receptors")
            lines = [f"{head} STA"]
            if grid.x_points is None and grid.y_points is None:
                lines.append(
                    f"{head} XYINC  {grid.x_init:12.2f} {grid.x_num:5d} {grid.x_delta:10.2f}  "
                    f"{grid.y_init:12.2f} {grid.y_num:5d} {grid.y_delta:10.2f}"
                )
            else:
                lines += _value_lines(f"{head} XPNTS", xs)
                lines += _value_lines(f"{head} YPNTS", ys)
            return [*lines, f"{head} END"]

        head = f"   GRIDPOLR  {name}"
        dists, dirs = grid.ring_distances(), grid.direction_angles()
        if not dists or not dirs:
            raise ValueError(f"polar grid {grid.grid_name} has no receptors")
        if grid.origin_source_id:
            # Written as the source's coordinates, which AERMOD and AERMAP
            # agree on only for a source placed at one point.
            origin = next((s for s in self.sources if s.source_id == grid.origin_source_id), None)
            if origin is None or origin.source_type.upper() not in _AERMAP_POINT_TYPES:
                raise ValueError(
                    f"polar grid {grid.grid_name} is centred on source {grid.origin_source_id!r}, "
                    "which is not a single-point source of this AERMAP project"
                )
            x0, y0 = origin.x_coord, origin.y_coord
        else:
            x0, y0 = grid.x_origin, grid.y_origin
        lines = [f"{head} STA", f"{head} ORIG  {x0:12.2f} {y0:12.2f}"]
        lines += _value_lines(f"{head} DIST", dists)
        if grid.directions is None:
            lines.append(f"{head} GDIR  {grid.dir_num:d} {grid.dir_init:.2f} {grid.dir_delta:.2f}")
        else:
            lines += _value_lines(f"{head} DDIR", dirs)
        return [*lines, f"{head} END"]

    def to_aermap_input(self) -> str:
        """Generate the AERMAP runstream (AERMAP 24142 syntax).

        Raises ``ValueError`` for a project AERMAP would reject or misread:
        no anchor point, no DEM file, no receptor and no source, an unknown
        ``terrain_type``, ``dem_format``, ``datum`` or source type, a
        partial domain, a source ID or grid name AERMAP would cut short, a
        line source without its end point (or a LINE without its width),
        or a ``PROVIDED`` project with a receptor or source that has no
        elevation, with grid receptors (the grid has no elevations to
        provide) or with no discrete receptor.
        """
        if self.anchor_x is None or self.anchor_y is None:
            raise ValueError("anchor_x and anchor_y must be provided for AERMAP's ANCHORXY")
        if not self.dem_files:
            raise ValueError("AERMAP needs at least one DEM file (dem_files)")
        has_receptors = bool(self.receptors or self.grid_receptor or self.grids)
        if not (has_receptors or self.sources):
            raise ValueError("AERMAP needs at least one receptor or source")
        self._network_names()

        terrhgts = self._terrhgts()
        provided = terrhgts == "PROVIDED"
        if provided:
            missing = [r.receptor_id for r in self.receptors if r.elevation is None]
            missing += [s.source_id for s in self.sources if s.elevation is None]
            if missing:
                raise ValueError(
                    "terrain_type='PROVIDED' needs an elevation on every receptor "
                    f"and source; missing on: {', '.join(missing)}"
                )
            if self.grid_receptor or self.grids:
                raise ValueError(
                    "terrain_type='PROVIDED' cannot be used with grid receptors: "
                    "the grid carries no elevations, and AERMAP would set them to 0"
                )
            if not self.receptors:
                raise ValueError(
                    "terrain_type='PROVIDED' needs at least one discrete receptor: "
                    "AERMAP computes hill heights for receptors and writes no "
                    "source file under PROVIDED"
                )

        anchor_utm_x = self.anchor_x if self.anchor_utm_x is None else self.anchor_utm_x
        anchor_utm_y = self.anchor_y if self.anchor_utm_y is None else self.anchor_utm_y

        lines = []

        # Header
        lines.append("** AERMAP Input File")
        lines.append(f"** {self.title_one}")
        if self.title_two:
            lines.append(f"** {self.title_two}")
        lines.append("**")
        lines.append("")

        # CO (Control) pathway
        lines.append("CO STARTING")
        lines.append(f"   TITLEONE  {self.title_one}")
        if self.title_two:
            lines.append(f"   TITLETWO  {self.title_two}")
        lines.append(f"   DATATYPE  {self._datatype()}")
        for dem_file in self.dem_files:
            lines.append(f"   DATAFILE  {_quote_field(str(dem_file), 'DEM file path')}")
        domain = self._domain_card()
        if domain:
            lines.append(domain)
        nadgrids = self._nadgrids_card()
        if nadgrids:
            lines.append(nadgrids)
        lines.append(
            f"   ANCHORXY  {self.anchor_x:.2f} {self.anchor_y:.2f} "
            f"{anchor_utm_x:.2f} {anchor_utm_y:.2f} {self.utm_zone} {self._datum_code()}"
        )
        lines.append(f"   TERRHGTS  {terrhgts}")
        lines.append("   RUNORNOT  RUN")
        lines.append("CO FINISHED")
        lines.append("")

        # SO (Source) pathway; AERMAP requires it before RE (SETORD, E120)
        if self.sources:
            lines.append("SO STARTING")
            for src in self.sources:
                lines.append(self._location_card(src, provided))
            lines.append("SO FINISHED")
            lines.append("")

        # RE (Receptor) pathway
        if has_receptors:
            lines.append("RE STARTING")

            # DISCCART takes x y [zelev]; AERMAP has no receptor IDs
            for rec in self.receptors:
                card = f"   DISCCART  {rec.x_coord:12.2f} {rec.y_coord:12.2f}"
                if provided:
                    card += f" {rec.elevation:10.2f}"
                lines.append(card)

            if self.grid_receptor:
                y_spacing = self.grid_spacing if self.grid_y_spacing is None else self.grid_y_spacing
                lines.append("   GRIDCART  GRID     STA")
                lines.append(
                    "   GRIDCART  GRID     XYINC  "
                    f"{self.grid_x_init:12.2f} {self.grid_x_num:5d} {self.grid_spacing:10.2f}  "
                    f"{self.grid_y_init:12.2f} {self.grid_y_num:5d} {y_spacing:10.2f}"
                )
                lines.append("   GRIDCART  GRID     END")

            for grid in self.grids:
                lines += self._grid_lines(grid)

            lines.append("RE FINISHED")
            lines.append("")

        # OU (Output) pathway: RECEPTOR needs receptors (E192) and
        # SOURCLOC needs sources (E190). AERMAP writes source elevations
        # only under EXTRACT; under PROVIDED it would leave the SOURCLOC
        # file empty (the source loop in aermap.f runs only if EXTRACT).
        lines.append("OU STARTING")
        if has_receptors:
            lines.append(f"   RECEPTOR  {_quote_field(self.receptor_output, 'receptor_output')}")
        if self.sources and not provided:
            lines.append(f"   SOURCLOC  {_quote_field(self.source_output, 'source_output')}")
        lines.append("OU FINISHED")
        lines.append("")

        return "\n".join(lines)

    def write(self, filename: str):
        """Write AERMAP input file"""
        content = self.to_aermap_input()
        with open(filename, 'w') as f:
            f.write(content)
        return filename


def create_grid_receptors_for_aermap(x_min: float, x_max: float,
                                      y_min: float, y_max: float,
                                      spacing: float) -> Tuple[float, float, int, int]:
    """
    Helper function to calculate grid parameters for AERMAP

    Args:
        x_min, x_max: X coordinate range
        y_min, y_max: Y coordinate range
        spacing: Grid spacing in meters

    Returns:
        Tuple of (x_init, y_init, x_num, y_num)
    """
    x_num = int((x_max - x_min) / spacing) + 1
    y_num = int((y_max - y_min) / spacing) + 1

    return x_min, y_min, x_num, y_num


# Example usage
if __name__ == "__main__":
    print("PyAERMOD AERMAP Input Generator")
    print("=" * 70)
    print()

    # Example 1: Discrete receptors
    print("Example 1: Discrete Receptors")
    print("-" * 70)

    project1 = AERMAPProject(
        job_id="DISCRETE_EXAMPLE",
        title_one="Discrete Receptor Terrain Processing",
        dem_files=["n41w088.dem", "n41w089.dem"],
        dem_format="NED",
        anchor_x=400000.0,
        anchor_y=4650000.0,
        utm_zone=16,
        datum="NAD83",
        terrain_type="EXTRACT"
    )

    # Add some receptors
    project1.add_receptor(AERMAPReceptor("R001", 401000.0, 4651000.0))
    project1.add_receptor(AERMAPReceptor("R002", 402000.0, 4651000.0))
    project1.add_receptor(AERMAPReceptor("R003", 403000.0, 4651000.0))

    # Add sources
    project1.add_source(AERMAPSource("STACK1", 401500.0, 4651500.0))

    filename1 = project1.write("aermap_discrete.inp")
    print(f"✓ Created: {filename1}")
    print(f"  Receptors: {len(project1.receptors)}")
    print(f"  Sources: {len(project1.sources)}")
    print()

    # Example 2: Grid receptors
    print("Example 2: Grid Receptors")
    print("-" * 70)

    project2 = AERMAPProject(
        job_id="GRID_EXAMPLE",
        title_one="Grid Receptor Terrain Processing",
        dem_files=["n41w088.dem"],
        dem_format="NED",
        anchor_x=400000.0,
        anchor_y=4650000.0,
        utm_zone=16,
        datum="NAD83",
        terrain_type="EXTRACT",
        grid_receptor=True,
        grid_x_init=400000.0,
        grid_y_init=4650000.0,
        grid_x_num=41,
        grid_y_num=41,
        grid_spacing=100.0
    )

    project2.add_source(AERMAPSource("STACK1", 402000.0, 4652000.0))

    filename2 = project2.write("aermap_grid.inp")
    print(f"✓ Created: {filename2}")
    print(f"  Grid: {project2.grid_x_num} × {project2.grid_y_num}")
    print(f"  Spacing: {project2.grid_spacing} m")
    print()

    print("=" * 70)
    print("To run AERMAP:")
    print("  aermap aermap_discrete.inp")
    print("  aermap aermap_grid.inp")
    print()
    print("AERMAP outputs:")
    print("  - Receptor file with elevations and hill heights")
    print("  - Source file with base elevations")
    print("  - <input stem>.out with the messages and AERMAP's completion banner")
    print()
    print("Note: You need DEM files covering your domain!")
    print("  Download from: https://www.usgs.gov/national-map-viewer")
    print()

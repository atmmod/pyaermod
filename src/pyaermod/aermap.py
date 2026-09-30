"""
PyAERMOD AERMAP Input Generator

Generates AERMAP input files for terrain preprocessing.
AERMAP is the EPA's terrain preprocessor for AERMOD.

AERMAP reads Digital Elevation Model (DEM) data and calculates:
- Receptor elevations
- Hill heights (for terrain-following calculations)
- Source elevations
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


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
    """Source definition for AERMAP"""
    source_id: str
    x_coord: float
    y_coord: float
    elevation: Optional[float] = None  # If None, AERMAP will calculate from DEM


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


@dataclass
class AERMAPProject:
    """
    AERMAP project configuration

    Generates terrain elevations for receptors and sources.

    ``to_aermap_input`` writes the runstream syntax of EPA's AERMAP 24142,
    the current release: the pathways in the order CO, SO, RE, OU, the
    mandatory ``ANCHORXY`` and ``RUNORNOT`` keywords, ``TERRHGTS EXTRACT``
    or ``PROVIDED``, and the ``RECEPTOR`` and ``SOURCLOC`` output files.

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
    hill heights, and the whole area must lie inside the DEM files
    (otherwise AERMAP stops with E310). Without it AERMAP uses the full
    extent of the DEM files.

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

    @classmethod
    def from_aermod_project(
        cls,
        aermod_project,
        dem_files: List[str],
        utm_zone: int = 16,
        datum: str = "NAD83",
        buffer: float = 1000.0,
        dem_format: Optional[str] = None,
    ) -> "AERMAPProject":
        """Create an AERMAPProject from an AERMODProject.

        Extracts source and receptor locations and builds corresponding
        AERMAP input for terrain elevation processing. The AERMOD
        coordinates are taken as UTM coordinates in ``utm_zone``, and the
        domain (``DOMAINXY``) is their extent widened by ``buffer`` on
        every side, so the DEM files must cover that whole area.

        Parameters
        ----------
        aermod_project : AERMODProject
        dem_files : list of str
            DEM file paths.
        utm_zone : int
        datum : str
        buffer : float
            Buffer in meters around domain extents.
        dem_format : str, optional
            ``"NED"`` (GeoTIFF) or ``"DEM"`` (USGS native format). By
            default ``"DEM"`` when every file ends in ``.dem``, otherwise
            ``"NED"``.

        Returns
        -------
        AERMAPProject
        """
        all_x, all_y = [], []
        for src in aermod_project.sources.sources:
            if hasattr(src, "x_coord"):
                all_x.append(src.x_coord)
                all_y.append(src.y_coord)
            elif hasattr(src, "x_start"):
                all_x.extend([src.x_start, src.x_end])
                all_y.extend([src.y_start, src.y_end])

        for grid in aermod_project.receptors.cartesian_grids:
            all_x.extend([
                grid.x_init,
                grid.x_init + (grid.x_num - 1) * grid.x_delta,
            ])
            all_y.extend([
                grid.y_init,
                grid.y_init + (grid.y_num - 1) * grid.y_delta,
            ])

        for rec in aermod_project.receptors.discrete_receptors:
            all_x.append(rec.x_coord)
            all_y.append(rec.y_coord)

        if not all_x:
            raise ValueError("No source or receptor coordinates found in project")

        x_min, y_min = min(all_x) - buffer, min(all_y) - buffer
        aermap = cls(
            title_one=f"AERMAP for {aermod_project.control.title_one}",
            dem_files=dem_files,
            dem_format=dem_format or _infer_dem_format(dem_files),
            # AERMOD coordinates are UTM: anchor a point to itself.
            anchor_x=x_min,
            anchor_y=y_min,
            utm_zone=utm_zone,
            datum=datum,
            terrain_type="EXTRACT",
            domain_x_min=x_min,
            domain_y_min=y_min,
            domain_x_max=max(all_x) + buffer,
            domain_y_max=max(all_y) + buffer,
        )

        for src in aermod_project.sources.sources:
            if hasattr(src, "x_coord"):
                aermap.add_source(AERMAPSource(src.source_id, src.x_coord, src.y_coord))
            elif hasattr(src, "x_start"):
                aermap.add_source(AERMAPSource(src.source_id, src.x_start, src.y_start))

        # AERMAPProject holds one grid; only the first is taken.
        for grid in aermod_project.receptors.cartesian_grids:
            aermap.grid_receptor = True
            aermap.grid_x_init = grid.x_init
            aermap.grid_y_init = grid.y_init
            aermap.grid_x_num = grid.x_num
            aermap.grid_y_num = grid.y_num
            aermap.grid_spacing = grid.x_delta
            aermap.grid_y_spacing = grid.y_delta
            break

        for i, rec in enumerate(aermod_project.receptors.discrete_receptors):
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

    def to_aermap_input(self) -> str:
        """Generate the AERMAP runstream (AERMAP 24142 syntax).

        Raises ``ValueError`` for a project AERMAP would reject: no anchor
        point, no DEM file, no receptor and no source, an unknown
        ``terrain_type``, ``dem_format`` or ``datum``, a partial domain, or
        a ``PROVIDED`` project with a receptor or source that has no
        elevation, with grid receptors (the grid has no elevations to
        provide) or with no discrete receptor.
        """
        if self.anchor_x is None or self.anchor_y is None:
            raise ValueError("anchor_x and anchor_y must be provided for AERMAP's ANCHORXY")
        if not self.dem_files:
            raise ValueError("AERMAP needs at least one DEM file (dem_files)")
        if not (self.receptors or self.grid_receptor or self.sources):
            raise ValueError("AERMAP needs at least one receptor or source")

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
            if self.grid_receptor:
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
                card = f"   LOCATION  {src.source_id:<12} POINT   {src.x_coord:12.2f} {src.y_coord:12.2f}"
                if provided:
                    card += f" {src.elevation:10.2f}"
                lines.append(card)
            lines.append("SO FINISHED")
            lines.append("")

        # RE (Receptor) pathway
        if self.receptors or self.grid_receptor:
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

            lines.append("RE FINISHED")
            lines.append("")

        # OU (Output) pathway: RECEPTOR needs receptors (E192) and
        # SOURCLOC needs sources (E190). AERMAP writes source elevations
        # only under EXTRACT; under PROVIDED it would leave the SOURCLOC
        # file empty (the source loop in aermap.f runs only if EXTRACT).
        lines.append("OU STARTING")
        if self.receptors or self.grid_receptor:
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

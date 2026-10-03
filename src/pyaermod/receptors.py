"""
PyAERMOD Receptor dataclasses.

Contains CartesianGrid, PolarGrid, DiscreteReceptor, and the
ReceptorPathway collection.

This module is an internal implementation detail.  Public imports should go
through :mod:`pyaermod.input_generator` (the backwards-compatible facade)
or :mod:`pyaermod.api`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from ._fields import described


def _fixed(number: str) -> str:
    """``number`` written out without an exponent or trailing zeros.

    setup.f STODBL takes an exponent only after a decimal point and only
    up to 30 in magnitude, so ``1e-05`` is E208; ``0.00001`` is read.
    """
    text = format(Decimal(number), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _num(value: float) -> str:
    """Ten significant digits, never in exponent form (see :func:`_fixed`)."""
    return _fixed(f"{value:.10g}")


def _exact(value: float) -> str:
    """The shortest text that reads back to the same float, no exponent."""
    return _fixed(repr(float(value)))


def _row_lines(keyword: str, grid_name: str, sub: str,
               rows: List[List[float]]) -> List[str]:
    """``KEYWORD name SUB row v1 v2 ...`` lines, six values to a line.

    reset.f (TERHGT / HILHGT / FLGHGT) tags every value with the row in
    the field after the sub-keyword and accumulates over records, so a
    row may span lines. A row of one repeated value is written as
    ``N*value`` on one line, which STODBL reads as N copies, with the
    value exact (:func:`_exact`): a grid of one elevation then takes a
    line per row. Other rows keep the one-decimal ``8.1f`` fields.
    """
    out: List[str] = []
    for row_idx, row in enumerate(rows, start=1):
        if len(row) > 1 and all(v == row[0] for v in row):
            out.append(f"   {keyword}  {grid_name:<8} {sub}  {row_idx:5d}  {len(row)}*{_exact(row[0])}")
            continue
        for start in range(0, len(row), 6):
            vals = " ".join(f"{v:8.1f}" for v in row[start:start + 6])
            out.append(f"   {keyword}  {grid_name:<8} {sub}  {row_idx:5d}  {vals}")
    return out


def _list_lines(keyword: str, grid_name: str, sub: str,
                values: List[float], per_line: int = 10) -> List[str]:
    """``KEYWORD name SUB v1 v2 ...`` lines; AERMOD accumulates over lines."""
    return [
        f"   {keyword}  {grid_name:<8} {sub}  "
        + "  ".join(_num(v) for v in values[start:start + per_line])
        for start in range(0, len(values), per_line)
    ]


@dataclass
class CartesianGrid:
    """
    AERMOD Cartesian receptor grid (GRIDCART)

    Creates a regular rectangular grid of receptors.
    """
    grid_name: str = field(default="GRID1", metadata=described(None, "Network ID, up to 8 characters"))

    # X-axis definition
    x_init: float = field(default=0.0, metadata=described("m", "x coordinate of the first column"))
    x_num: int = field(default=10, metadata=described("", "Number of columns"))
    x_delta: float = field(default=100.0, metadata=described("m", "Spacing between columns"))

    # Y-axis definition
    y_init: float = field(default=0.0, metadata=described("m", "y coordinate of the first row"))
    y_num: int = field(default=10, metadata=described("", "Number of rows"))
    y_delta: float = field(default=100.0, metadata=described("m", "Spacing between rows"))

    # One terrain elevation, hill height and flagpole height for every
    # receptor of the grid. Under elevated terrain a grid with neither
    # grid_elevations nor grid_hills gets GRIDCART ELEV and HILL rows
    # filled with z_elev and z_hill (reset.f RECART otherwise warns W214
    # and uses zero); with only one of the two row sets it is written
    # as given and AERMOD stops with E218. With CO FLAGPOLE a non-zero z_flag fills FLAG rows for a
    # grid without grid_flags; 0 leaves them out, and AERMOD gives every
    # receptor the FLAGPOLE height (W216), as for a DiscreteReceptor.
    # See to_aermod_input.
    z_elev: float = field(default=0.0, metadata=described("m", "Terrain elevation of every receptor"))
    z_hill: float = field(default=0.0, metadata=described("m", "Hill height scale of every receptor"))
    z_flag: float = field(default=0.0, metadata=described("m", "Flagpole height of every receptor"))

    # Per-receptor grid elevations from AERMAP (optional)
    # 2D arrays [row][col] where row = y-index, col = x-index
    grid_elevations: Optional[List[List[float]]] = None
    grid_hills: Optional[List[List[float]]] = None
    # Per-receptor flagpole heights (GRIDCART FLAG rows), same shape.
    grid_flags: Optional[List[List[float]]] = None

    # Explicit receptor coordinates (GRIDCART XPNTS / YPNTS). When set
    # they replace the x_init/x_num/x_delta (y_...) generator: AERMOD's
    # XYINC and XPNTS/YPNTS forms are exclusive within one network
    # (reset.f RECART, E180), and the writer emits whichever is in force.
    x_points: Optional[List[float]] = None
    y_points: Optional[List[float]] = None

    def x_values(self) -> List[float]:
        """The receptor x coordinates, explicit or generated."""
        if self.x_points is not None:
            return list(self.x_points)
        return [self.x_init + i * self.x_delta for i in range(self.x_num)]

    def y_values(self) -> List[float]:
        """The receptor y coordinates, explicit or generated."""
        if self.y_points is not None:
            return list(self.y_points)
        return [self.y_init + j * self.y_delta for j in range(self.y_num)]

    @property
    def receptor_count(self) -> int:
        return len(self.x_values()) * len(self.y_values())

    @classmethod
    def from_bounds(cls, x_min: float, x_max: float, y_min: float, y_max: float,
                   spacing: float = 100.0, grid_name: str = "GRID1") -> CartesianGrid:
        """Create grid from bounding box and spacing"""
        x_num = int((x_max - x_min) / spacing) + 1
        y_num = int((y_max - y_min) / spacing) + 1

        return cls(
            grid_name=grid_name,
            x_init=x_min,
            x_num=x_num,
            x_delta=spacing,
            y_init=y_min,
            y_num=y_num,
            y_delta=spacing
        )

    def _filled(self, value: float) -> List[List[float]]:
        """One row per y coordinate, one ``value`` per x coordinate."""
        n_x = len(self.x_values())
        return [[value] * n_x for _ in self.y_values()]

    def to_aermod_input(self, elevated: Optional[bool] = None,
                        flagpole: Optional[float] = None) -> str:
        """Generate AERMOD RE pathway text.

        AERMOD requires GRIDCART blocks wrapped in STA/END:
            GRIDCART  name  STA
                            XYINC  ...
            GRIDCART  name  END

        ``elevated`` is whether the run uses elevated terrain
        (:attr:`ControlPathway.elevated_terrain`) and ``flagpole`` the
        run's ``CO FLAGPOLE`` height (:attr:`ControlPathway.flag_pole_height`).
        Under elevated terrain a grid with neither ``grid_elevations``
        nor ``grid_hills`` gets ELEV and HILL rows of ``z_elev`` and
        ``z_hill``, because reset.f RECART needs both (W214 and zero
        heights when both are missing). A grid with only one of the two
        is written as given, and AERMOD stops with E218, as it does for
        a deck with ELEV rows and no HILL rows. With a flagpole height, a grid without
        ``grid_flags`` gets FLAG rows of a non-zero ``z_flag``; with
        ``z_flag`` 0 they are left out and AERMOD uses the FLAGPOLE
        height for every receptor (W216, the same heights), which keeps
        EPA's own FLAGPOLE decks reading back unchanged. Without that
        context (``None``, the default) only the rows given are written,
        as earlier releases did.
        """
        lines = [f"   GRIDCART  {self.grid_name:<8} STA"]
        if self.x_points is not None or self.y_points is not None:
            # Explicit coordinate lists; a missing side falls back to
            # the generator so the network is still complete.
            lines += _list_lines("GRIDCART", self.grid_name, "XPNTS", self.x_values())
            lines += _list_lines("GRIDCART", self.grid_name, "YPNTS", self.y_values())
        else:
            lines.append(
                f"                       XYINC  "
                f"{self.x_init:10.2f} {self.x_num:5d} {self.x_delta:8.2f}  "
                f"{self.y_init:10.2f} {self.y_num:5d} {self.y_delta:8.2f}"
            )
        # Per-receptor elevations / hill heights (from AERMAP) and
        # flagpole heights, one row (y index) per line group; the
        # grid-wide values fill the rows AERMOD needs and was not given.
        elevations, hills, flags = self.grid_elevations, self.grid_hills, self.grid_flags
        if elevated and elevations is None and hills is None:
            # Only when both sets are missing: with one given (say from
            # AERMAP) the other is not made up from z_elev / z_hill, and
            # AERMOD stops with E218 as it does on the original deck.
            elevations = self._filled(self.z_elev)
            hills = self._filled(self.z_hill)
        if flagpole is not None and flags is None and self.z_flag != 0.0:
            flags = self._filled(self.z_flag)
        for sub, rows in (("ELEV", elevations), ("HILL", hills), ("FLAG", flags)):
            if rows is not None:
                lines += _row_lines("GRIDCART", self.grid_name, sub, rows)
        lines.append(f"   GRIDCART  {self.grid_name:<8} END")
        return "\n".join(lines)


@dataclass
class PolarGrid:
    """
    AERMOD polar receptor grid (GRIDPOLR)

    Creates receptors in polar coordinates (distance and direction from origin).
    """
    grid_name: str = field(default="GRID1", metadata=described(None, "Network ID, up to 8 characters"))

    # Origin
    x_origin: float = field(default=0.0, metadata=described("m", "x coordinate of the centre"))
    y_origin: float = field(default=0.0, metadata=described("m", "y coordinate of the centre"))

    # Distance (radial)
    dist_init: float = field(default=100.0, metadata=described("m", "Distance of the first ring"))
    dist_num: int = field(default=10, metadata=described("", "Number of rings"))
    dist_delta: float = field(default=100.0, metadata=described("m", "Spacing between rings"))

    # Direction (degrees from north, clockwise)
    dir_init: float = field(default=0.0, metadata=described("deg", "First direction, clockwise from north"))
    dir_num: int = field(default=36, metadata=described("", "Number of directions"))
    dir_delta: float = field(default=10.0, metadata=described("deg", "Angle between directions"))

    # Explicit ring distances (GRIDPOLR DIST is only ever a list in
    # AERMOD: reset.f POLDST reads every field as a distance) and
    # explicit directions (GRIDPOLR DDIR). When set they replace the
    # dist_*/dir_* generators; the generated distances are written out
    # as the list AERMOD expects, and the generated directions as
    # ``GDIR num init delta`` (GENPOL's field order).
    distances: Optional[List[float]] = None
    directions: Optional[List[float]] = None

    # ``GRIDPOLR name ORIG srcid`` centres the network on a source
    # instead of on x_origin/y_origin (POLORG accepts either form).
    origin_source_id: Optional[str] = field(default=None, metadata=described(None, "Centre the grid on this source instead (ORIG srcid)"))

    # Per-receptor elevations, hill heights and flagpole heights
    # (GRIDPOLR ELEV / HILL / FLAG), one row per direction, one value
    # per ring distance.
    elevations: Optional[List[List[float]]] = None
    hills: Optional[List[List[float]]] = None
    flags: Optional[List[List[float]]] = None

    def ring_distances(self) -> List[float]:
        """The ring distances, explicit or generated."""
        if self.distances is not None:
            return list(self.distances)
        return [self.dist_init + k * self.dist_delta for k in range(self.dist_num)]

    def direction_angles(self) -> List[float]:
        """The radial directions in degrees, explicit or generated."""
        if self.directions is not None:
            return list(self.directions)
        return [self.dir_init + m * self.dir_delta for m in range(self.dir_num)]

    @property
    def receptor_count(self) -> int:
        return len(self.ring_distances()) * len(self.direction_angles())

    def to_aermod_input(self) -> str:
        """Generate AERMOD RE pathway text.

        AERMOD requires GRIDPOLR blocks wrapped in STA/END. The field
        layouts are those of reset.f: ``ORIG x y`` or ``ORIG srcid``,
        ``DIST d1 d2 ...`` (always a list), ``GDIR num init delta``
        (count first) or ``DDIR a1 a2 ...``. Before pyaermod 2.1 the
        writer emitted ``DIST init num delta`` and ``GDIR init num
        delta``; AERMOD read the former as three rings and the latter
        as zero directions, so the network had no receptors (RE E185).
        """
        name = self.grid_name
        lines = [f"   GRIDPOLR  {name:<8} STA"]
        if self.origin_source_id:
            lines.append(f"   GRIDPOLR  {name:<8} ORIG  {self.origin_source_id}")
        else:
            lines.append(
                f"   GRIDPOLR  {name:<8} ORIG  "
                f"{self.x_origin:10.2f} {self.y_origin:10.2f}"
            )
        lines += _list_lines("GRIDPOLR", name, "DIST", self.ring_distances())
        if self.directions is not None:
            lines += _list_lines("GRIDPOLR", name, "DDIR", self.directions)
        else:
            lines.append(
                f"   GRIDPOLR  {name:<8} GDIR  "
                f"{self.dir_num:d}  {_num(self.dir_init)}  {_num(self.dir_delta)}"
            )
        if self.elevations is not None:
            lines += _row_lines("GRIDPOLR", name, "ELEV", self.elevations)
        if self.hills is not None:
            lines += _row_lines("GRIDPOLR", name, "HILL", self.hills)
        if self.flags is not None:
            lines += _row_lines("GRIDPOLR", name, "FLAG", self.flags)
        lines.append(f"   GRIDPOLR  {name:<8} END")
        return "\n".join(lines)


@dataclass
class DiscreteReceptor:
    """Individual receptor at specific location.

    ``z_flag`` is the receptor's flagpole height; 0 means the run's
    ``CO FLAGPOLE`` default when there is one.
    """
    x_coord: float = field(metadata=described("m", "East (x) coordinate"))
    y_coord: float = field(metadata=described("m", "North (y) coordinate"))
    z_elev: float = field(default=0.0, metadata=described("m", "Terrain elevation"))
    z_hill: float = field(default=0.0, metadata=described("m", "Hill height scale"))
    z_flag: float = field(default=0.0, metadata=described("m", "Flagpole height"))
    label: str = field(default="", metadata=described(None, "A name for your own use; AERMOD never sees it"))  # Optional user-friendly name (not sent to AERMOD)

    def to_aermod_input(self, elevated: Optional[bool] = None,
                        flagpole: Optional[float] = None) -> str:
        """Generate AERMOD DISCCART line.

        reset.f DISCAR reads the fields after x and y by the run's
        options: ``zelev zhill [zflag]`` under elevated terrain and
        ``[zflag]`` under FLAT, the flagpole field only with CO FLAGPOLE.
        ``elevated`` (:attr:`ControlPathway.elevated_terrain`) and
        ``flagpole`` (:attr:`ControlPathway.flag_pole_height`) give that
        context. Under elevated terrain the line always carries
        ``zelev zhill``, a zero hill height included (a missing one is
        W228, and AERMOD then takes 0). With FLAGPOLE the flagpole field
        follows (after ``zelev zhill``, or straight after x and y under
        FLAT, where the elevation used to go and AERMOD read it as the
        flagpole height), and a zero ``z_flag`` is written as the
        FLAGPOLE height, the one AERMOD gives a receptor that has none.

        Under FLAT without FLAGPOLE, and with ``elevated=None`` (no
        context), the line is what earlier releases wrote: ``x y zelev``,
        plus ``zhill zflag`` when either is non-zero. AERMOD ignores the
        extra fields under FLAT (W229), but the elevation is kept in the
        deck so it reads back into ``z_elev``.
        """
        line = f"   DISCCART  {self.x_coord:12.4f} {self.y_coord:12.4f}"
        if elevated is None or (not elevated and flagpole is None):
            line += f" {self.z_elev:8.2f}"
            if self.z_hill != 0.0 or self.z_flag != 0.0:
                line += f" {self.z_hill:8.2f} {self.z_flag:8.2f}"
            return line
        if elevated:
            line += f" {self.z_elev:8.2f} {self.z_hill:8.2f}"
        if flagpole is not None:
            z_flag = self.z_flag if self.z_flag != 0.0 else flagpole
            line += f" {z_flag:8.2f}"
        return line


@dataclass
class ReceptorPathway:
    """Collection of receptor grids and discrete receptors"""
    cartesian_grids: List[CartesianGrid] = field(default_factory=list)
    polar_grids: List[PolarGrid] = field(default_factory=list)
    discrete_receptors: List[DiscreteReceptor] = field(default_factory=list)
    elevation_units: str = "METERS"

    def add_cartesian_grid(self, grid: CartesianGrid):
        """Add Cartesian grid"""
        self.cartesian_grids.append(grid)

    def add_polar_grid(self, grid: PolarGrid):
        """Add polar grid"""
        self.polar_grids.append(grid)

    def add_discrete_receptor(self, receptor: DiscreteReceptor):
        """Add discrete receptor"""
        self.discrete_receptors.append(receptor)

    def to_aermod_input(self, elevated: Optional[bool] = None,
                        flagpole: Optional[float] = None) -> str:
        """Generate AERMOD RE pathway text.

        ``elevated`` and ``flagpole`` are the run's terrain and flagpole
        options (:attr:`ControlPathway.elevated_terrain`,
        :attr:`ControlPathway.flag_pole_height`), which decide the
        elevation fields AERMOD reads; :meth:`AERMODProject.to_aermod_input`
        passes them. Without them the Cartesian grids and discrete
        receptors are written as earlier releases wrote them.
        """
        lines = ["RE STARTING"]

        # Elevation units (if not default)
        if self.elevation_units != "METERS":
            lines.append(f"   ELEVUNIT  {self.elevation_units}")

        # Cartesian grids
        for grid in self.cartesian_grids:
            lines.append(grid.to_aermod_input(elevated=elevated, flagpole=flagpole))

        # Polar grids
        for grid in self.polar_grids:
            lines.append(grid.to_aermod_input())

        # Discrete receptors
        for receptor in self.discrete_receptors:
            lines.append(receptor.to_aermod_input(elevated=elevated, flagpole=flagpole))

        lines.append("RE FINISHED")
        return "\n".join(lines)
